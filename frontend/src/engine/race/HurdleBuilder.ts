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
 */
import * as pc from 'playcanvas'
import { hurdlePositionsM } from '@shared/race/RaceTrackFeatures'
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
  /** Race distance — hurdle x-positions derive from this via shared fractions. */
  distanceM: number
  /** Full track width — hurdles span every lane. */
  trackWidthM: number
}

export class HurdleBuilder {
  private root: pc.Entity | null = null
  private materials: pc.StandardMaterial[] = []

  build(parent: pc.Entity, opts: HurdleBuildOptions): void {
    this.root = new pc.Entity('Hurdles')
    parent.addChild(this.root)

    const whiteMat = this.makeMaterial(1, 1, 1)
    const redMat = this.makeMaterial(STRIPE_RED_R, STRIPE_RED_G, STRIPE_RED_B)
    const postMat = this.makeMaterial(POST_GRAY, POST_GRAY, POST_GRAY)
    const shadowMat = this.makeMaterial(SHADOW_GRAY, SHADOW_GRAY, SHADOW_GRAY, SHADOW_OPACITY)

    for (const hurdleX of hurdlePositionsM(opts.distanceM)) {
      this.addHurdle(hurdleX, opts.trackWidthM, { whiteMat, redMat, postMat, shadowMat })
    }
  }

  destroy(): void {
    disposeEntity(this.root)
    this.root = null
    for (const mat of this.materials) safeDestroyMaterial(mat)
    this.materials = []
  }

  private addHurdle(
    x: number,
    trackWidthM: number,
    mats: {
      whiteMat: pc.StandardMaterial
      redMat: pc.StandardMaterial
      postMat: pc.StandardMaterial
      shadowMat: pc.StandardMaterial
    },
  ): void {
    // Shadow strip first — sells the bar's position on the ground plane.
    const shadow = new pc.Entity('HurdleShadow')
    shadow.addComponent('render', { type: 'plane' })
    shadow.render!.meshInstances[0].material = mats.shadowMat
    shadow.setLocalScale(SHADOW_DEPTH_M, 1, trackWidthM)
    shadow.setLocalPosition(x, SHADOW_Y_OFFSET, 0)
    this.root!.addChild(shadow)

    // Side posts at both track edges.
    const postZ = trackWidthM / 2 - POST_WIDTH_M / 2 - POST_INSET_M
    for (const z of [-postZ, postZ]) {
      const post = new pc.Entity('HurdlePost')
      post.addComponent('render', { type: 'box' })
      post.render!.meshInstances[0].material = mats.postMat
      post.setLocalScale(POST_WIDTH_M, BAR_HEIGHT_M + BAR_SECTION_M, POST_WIDTH_M)
      post.setLocalPosition(x, (BAR_HEIGHT_M + BAR_SECTION_M) / 2, z)
      this.root!.addChild(post)
    }

    // Striped crossbar: alternating red/white segments along Z. The last
    // segment is clipped to the remaining width so the bar always ends
    // flush with the post, whatever the lane count.
    let remaining = trackWidthM
    let segIndex = 0
    while (remaining > 0) {
      const segLen = Math.min(BAR_STRIPE_LENGTH_M, remaining)
      const zStart = trackWidthM / 2 - (trackWidthM - remaining)
      const segment = new pc.Entity('HurdleBar')
      segment.addComponent('render', { type: 'box' })
      segment.render!.meshInstances[0].material = segIndex % 2 === 0 ? mats.redMat : mats.whiteMat
      segment.setLocalScale(BAR_SECTION_M, BAR_SECTION_M, segLen)
      segment.setLocalPosition(x, BAR_HEIGHT_M, zStart - segLen / 2)
      this.root!.addChild(segment)
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
