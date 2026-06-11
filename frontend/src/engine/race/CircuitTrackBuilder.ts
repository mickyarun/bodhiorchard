// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * CircuitTrackBuilder — procedural organic-loop race track (one lap).
 *
 * The race distance is the loop's total length; geometry mirrors
 * TrackBuilder's visual language by importing its paint metrics + sand
 * palette:
 *   - One sand ribbon (RibbonMesh over LoopPath) spanning the full width.
 *   - `laneCount − 1` thin white lane-divider ribbons.
 *   - A solid white start line across the road at arc 0 (the world
 *     origin, tangent +X — same spot the straight track starts).
 *   - A checkered finish band placed just past arc = circumference via
 *     CircuitProjection poses, which wraps back to just past the start
 *     line — start and finish share the line, as on a real circuit.
 *
 * Deliberately omitted (vs TrackBuilder): the red/white outer kerbs and
 * the per-lane starting blocks — they assume straight-edge geometry and
 * earn their own curved treatment in a follow-up rather than a quick
 * distortion here. Trackside life lives in CircuitDecorBuilder.
 *
 * Ownership mirrors TrackBuilder: one root entity parents everything
 * (destroy() cascades), and the builder owns its materials plus the
 * custom ribbon meshes (entity teardown does not free mesh buffers).
 */
import * as pc from 'playcanvas'
import { LANE_WIDTH_M, MIN_RACERS, MAX_RACERS } from '@shared/race/RaceConstants'
import { laneCenterOffsetM } from '@shared/race/CircuitGeometry'
import {
  CHECKER_COLUMNS,
  CHECKER_ROWS,
  LANE_DIVIDER_WIDTH_M,
  PAINT_Y_OFFSET,
  SAND_B,
  SAND_G,
  SAND_R,
  START_LINE_DEPTH_M,
  type TrackBuildResult,
} from './TrackBuilder'
import { buildRibbonMesh } from './RibbonMesh'
import { CircuitProjection, entityYawDeg } from './TrackProjection'
import { disposeEntity, safeDestroyMaterial, safeDestroyMesh } from './dispose'

/**
 * Target chord length per ribbon segment. 0.75 m keeps the worst-case
 * chord-vs-arc error invisible at avatar scale even at the loop's
 * tightest curvature (~10.7 m radius), while a 200 m loop stays under
 * 300 quads per ribbon.
 */
const SEGMENT_ARC_M = 0.75

/** Floor on segment count so tiny loops never read as polygons. */
const MIN_SEGMENTS = 64

/**
 * The finish checker band wraps to just past arc 0, directly over the
 * full-circumference lane-divider ribbons — unlike the straight track,
 * where the band sits beyond the dividers' extent. A dedicated layer
 * above PAINT_Y_OFFSET (and below the boost pads at 0.02) stops the
 * band z-fighting the dividers running underneath it.
 */
const CHECKER_Y_OFFSET = 0.014

export interface CircuitTrackBuildOptions {
  /** Lap length in metres — the race distance IS the loop length. */
  circumferenceM: number
  /** Number of lanes — one per racer. Must be in [MIN_RACERS..MAX_RACERS]. */
  laneCount: number
}

export class CircuitTrackBuilder {
  private trackRoot: pc.Entity | null = null
  private materials: pc.StandardMaterial[] = []
  private meshes: pc.Mesh[] = []

  /**
   * Returns the same result contract as TrackBuilder so RaceScene's
   * consumers stay shape-agnostic: `laneCenterZs` are lane lateral
   * offsets from the centreline — numerically identical to the straight
   * track's lane-centre Zs (see LoopPath's anchoring note).
   */
  build(
    parent: pc.Entity,
    device: pc.GraphicsDevice,
    opts: CircuitTrackBuildOptions,
  ): TrackBuildResult {
    if (opts.laneCount < MIN_RACERS || opts.laneCount > MAX_RACERS) {
      throw new Error(
        `CircuitTrackBuilder: laneCount=${opts.laneCount} outside [${MIN_RACERS}..${MAX_RACERS}]`,
      )
    }
    if (opts.circumferenceM <= 0) {
      throw new Error(
        `CircuitTrackBuilder: circumferenceM must be positive, got ${opts.circumferenceM}`,
      )
    }

    const { circumferenceM, laneCount } = opts
    const trackWidthM = laneCount * LANE_WIDTH_M
    const segments = Math.max(MIN_SEGMENTS, Math.ceil(circumferenceM / SEGMENT_ARC_M))
    const projection = new CircuitProjection(circumferenceM)

    const root = new pc.Entity('CircuitTrack')
    parent.addChild(root)
    this.trackRoot = root

    const sandMat = this.makeMaterial(SAND_R, SAND_G, SAND_B, 0.06)
    const whiteMat = this.makeMaterial(1, 1, 1, 0.1)
    const darkMat = this.makeMaterial(0.08, 0.08, 0.08, 0.1)

    this.addSandRibbon(device, sandMat, circumferenceM, trackWidthM, segments)
    this.addLaneDividerRibbons(device, whiteMat, circumferenceM, trackWidthM, laneCount, segments)
    this.addStartLine(whiteMat, trackWidthM)
    this.addFinishChecker(whiteMat, darkMat, projection, circumferenceM, trackWidthM)

    const laneCenterZs = Array.from({ length: laneCount }, (_, i) =>
      laneCenterOffsetM(i, laneCount),
    )
    return { trackLengthM: circumferenceM, tileWidthM: trackWidthM, laneCenterZs }
  }

  destroy(): void {
    disposeEntity(this.trackRoot)
    this.trackRoot = null
    for (const mesh of this.meshes) safeDestroyMesh(mesh)
    this.meshes = []
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

  /**
   * One ribbon entity between two lateral edges. RibbonMesh vertices are
   * already in world space (LoopPath is anchored at the world origin),
   * so the entity sits at the origin — no centre offset like the old
   * annulus rings needed.
   */
  private addRibbon(
    device: pc.GraphicsDevice,
    material: pc.StandardMaterial,
    name: string,
    circumferenceM: number,
    lateralAM: number,
    lateralBM: number,
    segments: number,
    y: number,
  ): void {
    const mesh = buildRibbonMesh(device, { circumferenceM, lateralAM, lateralBM, segments, y })
    this.meshes.push(mesh)
    const meshInstance = new pc.MeshInstance(mesh, material)
    const entity = new pc.Entity(name)
    entity.addComponent('render', { meshInstances: [meshInstance] })
    this.trackRoot!.addChild(entity)
  }

  private addSandRibbon(
    device: pc.GraphicsDevice,
    mat: pc.StandardMaterial,
    circumferenceM: number,
    trackWidthM: number,
    segments: number,
  ): void {
    this.addRibbon(
      device, mat, 'RoadSandRibbon',
      circumferenceM, -trackWidthM / 2, trackWidthM / 2,
      segments, 0,
    )
  }

  /**
   * Divider i sits at lateral offset (i / laneCount − 0.5) · width — the
   * same between-lane positions TrackBuilder paints — as a thin ribbon
   * hugging the loop.
   */
  private addLaneDividerRibbons(
    device: pc.GraphicsDevice,
    mat: pc.StandardMaterial,
    circumferenceM: number,
    trackWidthM: number,
    laneCount: number,
    segments: number,
  ): void {
    for (let i = 1; i < laneCount; i++) {
      const lateralM = (i / laneCount - 0.5) * trackWidthM
      this.addRibbon(
        device, mat, 'LaneDividerRibbon',
        circumferenceM,
        lateralM - LANE_DIVIDER_WIDTH_M / 2, lateralM + LANE_DIVIDER_WIDTH_M / 2,
        segments, PAINT_Y_OFFSET,
      )
    }
  }

  /**
   * Arc 0 is the world origin with tangent +X — identical to the straight
   * track's start line, so the plane needs no rotation.
   */
  private addStartLine(mat: pc.StandardMaterial, trackWidthM: number): void {
    this.addPlane(mat, 'StartLine', 0, PAINT_Y_OFFSET, 0, 0, START_LINE_DEPTH_M, trackWidthM)
  }

  /**
   * Checker band just past arc = circumference (wraps to just past the
   * start line). Each square is a flat plane placed at its centre pose
   * and yawed to the local tangent — squares are small relative to the
   * curvature, so the chord approximation is invisible. The band starts
   * half a start-line depth after the line so the two read as distinct
   * markings, and sits on its own CHECKER_Y_OFFSET layer so it can't
   * z-fight the start line or the divider ribbons running beneath it.
   */
  private addFinishChecker(
    whiteMat: pc.StandardMaterial,
    darkMat: pc.StandardMaterial,
    projection: CircuitProjection,
    circumferenceM: number,
    trackWidthM: number,
  ): void {
    const squareW = trackWidthM / CHECKER_COLUMNS
    const bandStartArc = circumferenceM + START_LINE_DEPTH_M / 2
    for (let row = 0; row < CHECKER_ROWS; row++) {
      const arc = bandStartArc + row * squareW + squareW / 2
      for (let col = 0; col < CHECKER_COLUMNS; col++) {
        const isLight = (row + col) % 2 === 0
        const lateralM = (col + 0.5) * squareW - trackWidthM / 2
        const pose = projection.pose(arc, lateralM)
        this.addPlane(
          isLight ? whiteMat : darkMat, 'FinishChecker',
          pose.x, CHECKER_Y_OFFSET, pose.z,
          entityYawDeg(pose.headingDeg),
          squareW, squareW,
        )
      }
    }
  }

  private addPlane(
    material: pc.StandardMaterial,
    name: string,
    x: number,
    y: number,
    z: number,
    yawDeg: number,
    lengthX: number,
    widthZ: number,
  ): void {
    const entity = new pc.Entity(name)
    entity.addComponent('render', { type: 'plane' })
    entity.render!.meshInstances[0].material = material
    entity.setLocalScale(lengthX, 1, widthZ)
    entity.setLocalPosition(x, y, z)
    entity.setLocalEulerAngles(0, yawDeg, 0)
    this.trackRoot!.addChild(entity)
  }
}
