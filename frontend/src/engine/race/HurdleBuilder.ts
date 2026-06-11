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
 * HurdleBuilder — athletics-style hurdles across the track.
 *
 * One hurdle per entry from `hurdlePositionsM` (shared/race) so the bars
 * sit exactly where the server-side physics applies the clip penalty.
 * Each hurdle is two side posts plus a red/white striped crossbar at jump
 * height, with a soft shadow strip on the sand so the bar reads from the
 * low chase camera well before the avatar reaches it.
 *
 * Procedural boxes/planes, consistent with TrackBuilder. The builder owns
 * its materials and destroys them on teardown.
 *
 * Every element is placed through a TrackProjection: position AND yaw
 * come from the pose at (hurdleArc, lateralOffset). Posts and bar
 * segments are rigid boxes set at their centre pose — each segment is
 * short relative to the circuit's curvature, so the chord approximation
 * is invisible. On the straight track heading is 0 everywhere and the
 * output is identical to the pre-projection builder.
 */
import * as pc from 'playcanvas'
import { hurdlePositionsM } from '@shared/race/RaceTrackFeatures'
import { entityYawDeg, type TrackProjection } from './TrackProjection'
import { disposeEntity, safeDestroyMaterial } from './dispose'

/** Crossbar height — proportioned to the ~0.9m race avatars. */
const BAR_HEIGHT_M = 0.42

/** Crossbar cross-section (depth along X, thickness along Y). */
const BAR_SECTION_M = 0.09

/** Alternating stripe length along the bar (Z). */
const BAR_STRIPE_LENGTH_M = 0.75

/** Side posts. */
const POST_WIDTH_M = 0.12
const POST_INSET_M = 0.05

/** Ground shadow strip under the bar. */
const SHADOW_DEPTH_M = 0.5
const SHADOW_Y_OFFSET = 0.018

/** Palette: warning red + white stripes on dark posts. */
const STRIPE_RED_R = 0.85
const STRIPE_RED_G = 0.2
const STRIPE_RED_B = 0.2
const POST_GRAY = 0.16
/** Shadow is a translucent dark strip — opacity keeps the sand visible. */
const SHADOW_GRAY = 0.05
const SHADOW_OPACITY = 0.28

export interface HurdleBuildOptions {
  /**
   * Physical loop length — hurdle arc positions derive from this via the
   * shared fractions. On the circuit this is LOOP_LENGTH_M, so the bars
   * are placed once on the loop and crossed once per lap; on the straight
   * track it's the full race distance.
   */
  loopLengthM: number
  /** Full track width — hurdles span every lane. */
  trackWidthM: number
  /** Shape-specific arc → world mapping; positions AND yaws every element. */
  projection: TrackProjection
}

export class HurdleBuilder {
  private root: pc.Entity | null = null
  private materials: pc.StandardMaterial[] = []
  private projection: TrackProjection | null = null

  build(parent: pc.Entity, opts: HurdleBuildOptions): void {
    this.root = new pc.Entity('Hurdles')
    parent.addChild(this.root)
    this.projection = opts.projection

    const whiteMat = this.makeMaterial(1, 1, 1)
    const redMat = this.makeMaterial(STRIPE_RED_R, STRIPE_RED_G, STRIPE_RED_B)
    const postMat = this.makeMaterial(POST_GRAY, POST_GRAY, POST_GRAY)
    const shadowMat = this.makeMaterial(SHADOW_GRAY, SHADOW_GRAY, SHADOW_GRAY, SHADOW_OPACITY)

    for (const hurdleArcM of hurdlePositionsM(opts.loopLengthM)) {
      this.addHurdle(hurdleArcM, opts.trackWidthM, { whiteMat, redMat, postMat, shadowMat })
    }
  }

  destroy(): void {
    disposeEntity(this.root)
    this.root = null
    for (const mat of this.materials) safeDestroyMaterial(mat)
    this.materials = []
    this.projection = null
  }

  /**
   * Place one render-component entity at (arc, lateral), yawed to the
   * local travel tangent. Straight track: heading 0 → yaw 0, matching
   * the original unrotated boxes/planes byte-for-byte.
   */
  private addPiece(
    name: string,
    renderType: 'box' | 'plane',
    material: pc.StandardMaterial,
    arcM: number,
    lateralM: number,
    y: number,
    scale: { x: number; y: number; z: number },
  ): void {
    const pose = this.projection!.pose(arcM, lateralM)
    const entity = new pc.Entity(name)
    entity.addComponent('render', { type: renderType })
    entity.render!.meshInstances[0].material = material
    entity.setLocalScale(scale.x, scale.y, scale.z)
    entity.setLocalPosition(pose.x, y, pose.z)
    entity.setLocalEulerAngles(0, entityYawDeg(pose.headingDeg), 0)
    this.root!.addChild(entity)
  }

  private addHurdle(
    arcM: number,
    trackWidthM: number,
    mats: {
      whiteMat: pc.StandardMaterial
      redMat: pc.StandardMaterial
      postMat: pc.StandardMaterial
      shadowMat: pc.StandardMaterial
    },
  ): void {
    // Shadow strip first — sells the bar's position on the ground plane.
    this.addPiece('HurdleShadow', 'plane', mats.shadowMat, arcM, 0, SHADOW_Y_OFFSET, {
      x: SHADOW_DEPTH_M, y: 1, z: trackWidthM,
    })

    // Side posts at both track edges.
    const postOffsetM = trackWidthM / 2 - POST_WIDTH_M / 2 - POST_INSET_M
    for (const lateralM of [-postOffsetM, postOffsetM]) {
      this.addPiece('HurdlePost', 'box', mats.postMat, arcM, lateralM,
        (BAR_HEIGHT_M + BAR_SECTION_M) / 2,
        { x: POST_WIDTH_M, y: BAR_HEIGHT_M + BAR_SECTION_M, z: POST_WIDTH_M })
    }

    // Striped crossbar: alternating red/white segments across the track
    // (local Z = lateral direction once yawed). The last segment is
    // clipped to the remaining width so the bar always ends flush with
    // the post, whatever the lane count.
    let remaining = trackWidthM
    let segIndex = 0
    while (remaining > 0) {
      const segLen = Math.min(BAR_STRIPE_LENGTH_M, remaining)
      const lateralStart = trackWidthM / 2 - (trackWidthM - remaining)
      this.addPiece('HurdleBar', 'box',
        segIndex % 2 === 0 ? mats.redMat : mats.whiteMat,
        arcM, lateralStart - segLen / 2, BAR_HEIGHT_M,
        { x: BAR_SECTION_M, y: BAR_SECTION_M, z: segLen })
      remaining -= segLen
      segIndex++
    }
  }

  private makeMaterial(r: number, g: number, b: number, opacity = 1): pc.StandardMaterial {
    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(r, g, b)
    mat.metalness = 0
    mat.gloss = 0.15
    if (opacity < 1) {
      mat.opacity = opacity
      mat.blendType = pc.BLEND_NORMAL
    }
    mat.update()
    this.materials.push(mat)
    return mat
  }
}
