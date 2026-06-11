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
 * CircuitTrackBuilder — procedural circular race track (one lap).
 *
 * The race distance is the circumference; geometry mirrors TrackBuilder's
 * visual language by importing its paint metrics + sand palette:
 *   - One sand annulus spanning the full track width.
 *   - `laneCount − 1` thin white lane-divider rings.
 *   - A solid white start line across the road at arc 0 (the world
 *     origin, tangent +X — same spot the straight track starts).
 *   - A checkered finish band placed just past arc = circumference via
 *     CircuitProjection poses, which wraps back to just past the start
 *     line — start and finish share the line, as on a real circuit.
 *
 * Deliberately omitted for circuit v1 (vs TrackBuilder): the red/white
 * outer kerbs, the per-lane starting blocks, and DecorBuilder props —
 * they all assume straight-edge geometry and earn their own curved
 * treatment in a follow-up rather than a quick distortion here.
 *
 * Ownership mirrors TrackBuilder: one root entity parents everything
 * (destroy() cascades), and the builder owns its materials plus the
 * custom annulus meshes (entity teardown does not free mesh buffers).
 */
import * as pc from 'playcanvas'
import { LANE_WIDTH_M, MIN_RACERS, MAX_RACERS } from '@shared/race/RaceConstants'
import { circuitRadiusM, laneCenterOffsetM } from '@shared/race/CircuitGeometry'
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
import { buildAnnulusMesh } from './AnnulusMesh'
import { CircuitProjection, entityYawDeg } from './TrackProjection'
import { disposeEntity, safeDestroyMaterial, safeDestroyMesh } from './dispose'

/**
 * Target chord length per annulus segment. 0.75 m keeps the worst-case
 * chord-vs-arc error under ~5 mm at the 100 m circuit's inner edge —
 * invisible at avatar scale — while a 200 m ring stays under 300 quads.
 */
const SEGMENT_ARC_M = 0.75

/** Floor on segment count so tiny rings never read as polygons. */
const MIN_SEGMENTS = 64

export interface CircuitTrackBuildOptions {
  /** Lap length in metres — the race distance IS the circumference. */
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
   * track's lane-centre Zs (see CircuitGeometry's anchoring note).
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
    const radiusM = circuitRadiusM(circumferenceM)
    const segments = Math.max(MIN_SEGMENTS, Math.ceil(circumferenceM / SEGMENT_ARC_M))
    const projection = new CircuitProjection(circumferenceM)

    const root = new pc.Entity('CircuitTrack')
    parent.addChild(root)
    this.trackRoot = root

    const sandMat = this.makeMaterial(SAND_R, SAND_G, SAND_B, 0.06)
    const whiteMat = this.makeMaterial(1, 1, 1, 0.1)
    const darkMat = this.makeMaterial(0.08, 0.08, 0.08, 0.1)

    this.addSandRing(device, sandMat, radiusM, trackWidthM, segments)
    this.addLaneDividerRings(device, whiteMat, radiusM, trackWidthM, laneCount, segments)
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
   * One ring entity: annulus mesh centred on the circle's centre, which
   * sits at world (0, radius) — see CircuitGeometry's anchoring (arc 0
   * is the world origin, circle curving toward +Z).
   */
  private addRing(
    device: pc.GraphicsDevice,
    material: pc.StandardMaterial,
    name: string,
    innerRadiusM: number,
    outerRadiusM: number,
    segments: number,
    y: number,
    centreRadiusM: number,
  ): void {
    const mesh = buildAnnulusMesh(device, innerRadiusM, outerRadiusM, segments, y)
    this.meshes.push(mesh)
    const meshInstance = new pc.MeshInstance(mesh, material)
    const entity = new pc.Entity(name)
    entity.addComponent('render', { meshInstances: [meshInstance] })
    entity.setLocalPosition(0, 0, centreRadiusM)
    this.trackRoot!.addChild(entity)
  }

  private addSandRing(
    device: pc.GraphicsDevice,
    mat: pc.StandardMaterial,
    radiusM: number,
    trackWidthM: number,
    segments: number,
  ): void {
    this.addRing(
      device, mat, 'RoadSandRing',
      radiusM - trackWidthM / 2, radiusM + trackWidthM / 2,
      segments, 0, radiusM,
    )
  }

  /**
   * Divider ring i sits at lateral offset (i / laneCount − 0.5) · width —
   * the same between-lane positions TrackBuilder paints. A positive
   * lateral offset is toward the circle centre, so its ring radius is
   * `radius − offset` (matches circuitPose's lane radius).
   */
  private addLaneDividerRings(
    device: pc.GraphicsDevice,
    mat: pc.StandardMaterial,
    radiusM: number,
    trackWidthM: number,
    laneCount: number,
    segments: number,
  ): void {
    for (let i = 1; i < laneCount; i++) {
      const lateralM = (i / laneCount - 0.5) * trackWidthM
      const ringRadiusM = radiusM - lateralM
      this.addRing(
        device, mat, 'LaneDividerRing',
        ringRadiusM - LANE_DIVIDER_WIDTH_M / 2, ringRadiusM + LANE_DIVIDER_WIDTH_M / 2,
        segments, PAINT_Y_OFFSET, radiusM,
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
   * half a start-line depth after the line so the two paint layers never
   * overlap (they share PAINT_Y_OFFSET and would z-fight).
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
          pose.x, PAINT_Y_OFFSET, pose.z,
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
