// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * TrackBuilder — procedural sand race track with painted white lane lines.
 *
 * Composition (all sizes are derived from `build(opts)`, not compile-time
 * constants, so a single `RaceRoom` can spin up a 100 m 2-lane sprint or a
 * 200 m 10-lane dash without code changes):
 *   - One flat sand-coloured rectangle for the road surface
 *     (`distanceM × laneCount·LANE_WIDTH_M`).
 *   - `laneCount − 1` white stripes down the length, one between each pair
 *     of adjacent lanes.
 *   - A solid white start line across the road at `x = 0`.
 *   - A checkered finish band (two rows of alternating light/dark squares)
 *     at `x = distanceM`.
 *
 * All geometry is procedural `pc.Plane` meshes — no GLB assets used. Means
 * the track width and length are both flow-parameters; only the palette,
 * paint thickness and checker density stay as named tuning constants here.
 *
 * Ownership:
 *   - `trackRoot` entity parents every track element — destroy() cascades.
 *   - Three `pc.StandardMaterial` instances (sand, white, dark) are owned
 *     here and destroyed in destroy().
 */
import * as pc from 'playcanvas'
import { LANE_WIDTH_M, MIN_RACERS, MAX_RACERS } from '@shared/race/RaceConstants'
import { disposeEntity, safeDestroyMaterial } from './dispose'

/** Thickness of the painted lane-divider stripes. */
const LANE_DIVIDER_WIDTH_M = 0.18

/** Thickness of the start line painted across the road. */
const START_LINE_DEPTH_M = 0.5

/** All white-paint geometry sits this far above the sand to avoid z-fighting. */
const PAINT_Y_OFFSET = 0.01

/** Sand colour — warm beige, mid-gloss. Matches the village SandRoadBuilder family. */
const SAND_R = 0.92
const SAND_G = 0.84
const SAND_B = 0.64

/** Finish-band checker: number of squares across the width and rows deep. */
const CHECKER_COLUMNS = 10
const CHECKER_ROWS = 2

/**
 * Red/white kerb stripes along the outer track edges — the single biggest
 * readability upgrade for a straight track. Each segment is 2 m long and
 * alternates colour, matching how real rally/formula kerbs look.
 */
const KERB_SEGMENT_LENGTH_M = 2.0
const KERB_DEPTH_M = 0.4
const KERB_OUTSET_M = 0.05        // nudge kerb outward so it doesn't overlap paint
const KERB_Y_OFFSET = 0.015       // sits above sand, below paint
const KERB_RED_R = 0.82
const KERB_RED_G = 0.18
const KERB_RED_B = 0.18

/**
 * Starting blocks — a row of small colored boxes behind the start line,
 * one per lane. Reads as "racers line up here" even before the camera
 * resolves the avatars.
 */
const START_BLOCK_LENGTH_M = 0.6
const START_BLOCK_HEIGHT_M = 0.22
const START_BLOCK_Y_OFFSET = 0.01
const START_BLOCK_X_BACKSET_M = 1.2  // positioned at x = -backset (just behind start)
/** Colour-per-lane palette — cycles if more than 6 lanes. */
const START_BLOCK_COLORS: Array<[number, number, number]> = [
  [0.95, 0.30, 0.30], // red
  [0.30, 0.60, 0.95], // blue
  [0.95, 0.80, 0.30], // yellow
  [0.40, 0.85, 0.50], // green
  [0.85, 0.45, 0.90], // violet
  [0.95, 0.55, 0.25], // orange
]

export interface TrackBuildOptions {
  /** Race distance in metres along +X. Start at x=0, finish at x=distanceM. */
  distanceM: number
  /** Number of lanes — one per racer. Must be in [MIN_RACERS..MAX_RACERS]. */
  laneCount: number
}

export interface TrackBuildResult {
  /** Length in metres from start line to finish line. */
  trackLengthM: number
  /** Full visible width of the road, consumed by lane-placement logic. */
  tileWidthM: number
  /**
   * Z coordinate of the centre of each lane. Racer avatars should sit on
   * these exact values so they line up with the painted dividers.
   */
  laneCenterZs: number[]
}

export class TrackBuilder {
  private trackRoot: pc.Entity | null = null
  private materials: pc.StandardMaterial[] = []

  // Loader param kept for interface symmetry with the previous Kenney-based
  // builder so RaceScene wiring stays unchanged. Procedural geometry doesn't
  // actually need it.
  constructor(_loader: unknown) {
    void _loader
  }

  async build(parent: pc.Entity, opts: TrackBuildOptions): Promise<TrackBuildResult> {
    if (opts.laneCount < MIN_RACERS || opts.laneCount > MAX_RACERS) {
      throw new Error(
        `TrackBuilder: laneCount=${opts.laneCount} outside [${MIN_RACERS}..${MAX_RACERS}]`,
      )
    }
    if (opts.distanceM <= 0) {
      throw new Error(`TrackBuilder: distanceM must be positive, got ${opts.distanceM}`)
    }

    const { distanceM, laneCount } = opts
    const trackWidthM = laneCount * LANE_WIDTH_M

    const root = new pc.Entity('RaceTrack')
    parent.addChild(root)
    this.trackRoot = root

    const sandMat = this.makeMaterial(SAND_R, SAND_G, SAND_B, 0.06)
    const whiteMat = this.makeMaterial(1, 1, 1, 0.1)
    const darkMat = this.makeMaterial(0.08, 0.08, 0.08, 0.1)
    const redMat = this.makeMaterial(KERB_RED_R, KERB_RED_G, KERB_RED_B, 0.08)

    this.addSandSurface(sandMat, distanceM, trackWidthM)
    this.addLaneDividers(whiteMat, distanceM, trackWidthM, laneCount)
    this.addOuterKerbs(whiteMat, redMat, distanceM, trackWidthM)
    this.addStartLine(whiteMat, trackWidthM)
    this.addStartingBlocks(distanceM, trackWidthM, laneCount)
    this.addFinishChecker(whiteMat, darkMat, distanceM, trackWidthM)

    // Centre of each lane — the painted dividers sit between these values.
    const laneCenterZs = Array.from(
      { length: laneCount },
      (_, i) => (i + 0.5) * LANE_WIDTH_M - trackWidthM / 2,
    )

    return { trackLengthM: distanceM, tileWidthM: trackWidthM, laneCenterZs }
  }

  destroy(): void {
    disposeEntity(this.trackRoot)
    this.trackRoot = null
    for (const mat of this.materials) safeDestroyMaterial(mat)
    this.materials = []
  }

  private makeMaterial(r: number, g: number, b: number, gloss: number): pc.StandardMaterial {
    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(r, g, b)
    mat.metalness = 0
    mat.gloss = gloss
    mat.update()
    this.materials.push(mat)
    return mat
  }

  private addPlane(material: pc.StandardMaterial, name: string, x: number, y: number, z: number, lengthX: number, widthZ: number): void {
    const entity = new pc.Entity(name)
    entity.addComponent('render', { type: 'plane' })
    entity.render!.meshInstances[0].material = material
    entity.setLocalScale(lengthX, 1, widthZ)
    entity.setLocalPosition(x, y, z)
    this.trackRoot!.addChild(entity)
  }

  private addSandSurface(mat: pc.StandardMaterial, distanceM: number, trackWidthM: number): void {
    this.addPlane(mat, 'RoadSand', distanceM / 2, 0, 0, distanceM, trackWidthM)
  }

  private addLaneDividers(mat: pc.StandardMaterial, distanceM: number, trackWidthM: number, laneCount: number): void {
    // Dividers sit between lanes: for N lanes there are N-1 dividers at
    // z = (i / laneCount - 0.5) * trackWidthM for i in 1..N-1.
    for (let i = 1; i < laneCount; i++) {
      const z = (i / laneCount - 0.5) * trackWidthM
      this.addPlane(mat, 'LaneDivider', distanceM / 2, PAINT_Y_OFFSET, z, distanceM, LANE_DIVIDER_WIDTH_M)
    }
  }

  private addStartLine(mat: pc.StandardMaterial, trackWidthM: number): void {
    this.addPlane(mat, 'StartLine', 0, PAINT_Y_OFFSET, 0, START_LINE_DEPTH_M, trackWidthM)
  }

  /**
   * Red/white alternating kerbs painted just outside the outer-most lanes.
   * Each segment is KERB_SEGMENT_LENGTH_M long; the segment count rounds
   * up so the last segment clips at the finish line rather than leaving a
   * visible gap.
   */
  private addOuterKerbs(
    whiteMat: pc.StandardMaterial,
    redMat: pc.StandardMaterial,
    distanceM: number,
    trackWidthM: number,
  ): void {
    const segments = Math.ceil(distanceM / KERB_SEGMENT_LENGTH_M)
    const outerZ = trackWidthM / 2 + KERB_OUTSET_M
    for (let i = 0; i < segments; i++) {
      const centerX = i * KERB_SEGMENT_LENGTH_M + KERB_SEGMENT_LENGTH_M / 2
      const mat = i % 2 === 0 ? redMat : whiteMat
      for (const side of [-outerZ, outerZ]) {
        this.addPlane(
          mat, 'Kerb',
          centerX, KERB_Y_OFFSET,
          side + (side > 0 ? KERB_DEPTH_M / 2 : -KERB_DEPTH_M / 2),
          KERB_SEGMENT_LENGTH_M, KERB_DEPTH_M,
        )
      }
    }
  }

  /**
   * One coloured block per lane, positioned at x = -START_BLOCK_X_BACKSET_M
   * (just behind the start line). Reads as "racer lineup" even before
   * the skinned avatars load.
   */
  private addStartingBlocks(distanceM: number, trackWidthM: number, laneCount: number): void {
    void distanceM
    for (let lane = 0; lane < laneCount; lane++) {
      const [r, g, b] = START_BLOCK_COLORS[lane % START_BLOCK_COLORS.length]
      const mat = this.makeMaterial(r, g, b, 0.12)
      const z = (lane + 0.5) * (trackWidthM / laneCount) - trackWidthM / 2
      const entity = new pc.Entity('StartBlock')
      entity.addComponent('render', { type: 'box' })
      entity.render!.meshInstances[0].material = mat
      entity.setLocalScale(START_BLOCK_LENGTH_M, START_BLOCK_HEIGHT_M, START_BLOCK_LENGTH_M * 1.1)
      entity.setLocalPosition(
        -START_BLOCK_X_BACKSET_M,
        START_BLOCK_HEIGHT_M / 2 + START_BLOCK_Y_OFFSET,
        z,
      )
      this.trackRoot!.addChild(entity)
    }
  }

  private addFinishChecker(whiteMat: pc.StandardMaterial, darkMat: pc.StandardMaterial, distanceM: number, trackWidthM: number): void {
    const squareW = trackWidthM / CHECKER_COLUMNS
    // Place CHECKER_ROWS × CHECKER_COLUMNS squares at the finish, alternating
    // light/dark like a racing flag. Origin of the band is the finish line.
    for (let row = 0; row < CHECKER_ROWS; row++) {
      const rowX = distanceM + row * squareW + squareW / 2
      for (let col = 0; col < CHECKER_COLUMNS; col++) {
        const isLight = (row + col) % 2 === 0
        const z = (col + 0.5) * squareW - trackWidthM / 2
        this.addPlane(
          isLight ? whiteMat : darkMat,
          'FinishChecker',
          rowX,
          PAINT_Y_OFFSET,
          z,
          squareW,
          squareW,
        )
      }
    }
  }
}
