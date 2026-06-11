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
 * BoostPadBuilder — glowing speed strips painted across the track.
 *
 * One pad per entry from `boostPadPositionsM` (shared/race) so the visuals
 * sit exactly where the server-side physics grants the boost. Each pad is
 * an emissive cyan base strip plus forward-pointing chevrons; `update(dt)`
 * pulses the emissive intensity so pads read as "live" pickups from the
 * chase camera.
 *
 * All geometry is procedural planes, consistent with TrackBuilder. The
 * builder owns its two emissive materials and destroys them on teardown.
 *
 * Every element is placed through a TrackProjection: position AND yaw
 * come from the pose at (featureArc, lateralOffset). Strips/chevrons are
 * flat planes set at their centre pose — they're small relative to the
 * circuit's curvature, so the chord approximation is invisible. On the
 * straight track heading is 0 everywhere and output is identical to the
 * pre-projection builder.
 */
import * as pc from 'playcanvas'
import { boostPadPositionsM } from '@shared/race/RaceTrackFeatures'
import { entityYawDeg, type TrackProjection } from './TrackProjection'
import { disposeEntity, safeDestroyMaterial } from './dispose'

/** Strip footprint along the running direction. */
const PAD_DEPTH_M = 1.4

/** Pads sit above the kerb/paint layers to avoid z-fighting. */
const PAD_Y_OFFSET = 0.02
const CHEVRON_Y_OFFSET = 0.025

/** Cyan glow — base strip is dimmer than the chevrons sitting on it. */
const PAD_COLOR_R = 0.16
const PAD_COLOR_G = 0.78
const PAD_COLOR_B = 0.92

/** Chevrons: arm geometry, count, and spacing along the strip. */
const CHEVRON_COUNT = 3
const CHEVRON_ARM_LENGTH_M = 0.55
const CHEVRON_ARM_WIDTH_M = 0.14
const CHEVRON_SPACING_M = 0.42
const CHEVRON_ANGLE_DEG = 38

/** Emissive pulse: intensity oscillates base ± swing at the given rate. */
const PULSE_BASE_INTENSITY = 1.4
const PULSE_SWING = 0.7
const PULSE_HZ = 0.9

export interface BoostPadBuildOptions {
  /** Race distance — pad arc positions derive from this via shared fractions. */
  distanceM: number
  /** Full track width — pads span every lane (auto-trigger on cross). */
  trackWidthM: number
  /** Shape-specific arc → world mapping; positions AND yaws every element. */
  projection: TrackProjection
}

export class BoostPadBuilder {
  private root: pc.Entity | null = null
  private baseMat: pc.StandardMaterial | null = null
  private chevronMat: pc.StandardMaterial | null = null
  private projection: TrackProjection | null = null
  private pulseT = 0

  build(parent: pc.Entity, opts: BoostPadBuildOptions): void {
    this.root = new pc.Entity('BoostPads')
    parent.addChild(this.root)
    this.projection = opts.projection

    this.baseMat = this.makeEmissiveMaterial(0.55)
    this.chevronMat = this.makeEmissiveMaterial(1.0)

    for (const padArcM of boostPadPositionsM(opts.distanceM)) {
      this.addPad(padArcM, opts.trackWidthM)
    }
  }

  /** Per-frame emissive pulse — call from the scene's update handler. */
  update(dtSec: number): void {
    if (!this.baseMat || !this.chevronMat) return
    this.pulseT += dtSec
    const wave = Math.sin(this.pulseT * Math.PI * 2 * PULSE_HZ)
    const intensity = PULSE_BASE_INTENSITY + wave * PULSE_SWING
    this.baseMat.emissiveIntensity = intensity * 0.55
    this.chevronMat.emissiveIntensity = intensity
    this.baseMat.update()
    this.chevronMat.update()
  }

  destroy(): void {
    disposeEntity(this.root)
    this.root = null
    safeDestroyMaterial(this.baseMat)
    safeDestroyMaterial(this.chevronMat)
    this.baseMat = null
    this.chevronMat = null
    this.projection = null
  }

  private addPad(padArcM: number, trackWidthM: number): void {
    this.addPlane(this.baseMat!, 'BoostPadStrip', padArcM, PAD_Y_OFFSET, 0, 0, PAD_DEPTH_M, trackWidthM)

    // Chevrons point in the running direction: each is two arms angled
    // toward the centreline, staggered along the strip arc.
    const firstArcM = padArcM - ((CHEVRON_COUNT - 1) / 2) * CHEVRON_SPACING_M
    for (let i = 0; i < CHEVRON_COUNT; i++) {
      const arcM = firstArcM + i * CHEVRON_SPACING_M
      const armOffsetM = CHEVRON_ARM_LENGTH_M / 2 - CHEVRON_ARM_WIDTH_M / 2
      this.addPlane(this.chevronMat!, 'BoostChevron', arcM, CHEVRON_Y_OFFSET, -armOffsetM, CHEVRON_ANGLE_DEG, CHEVRON_ARM_LENGTH_M, CHEVRON_ARM_WIDTH_M)
      this.addPlane(this.chevronMat!, 'BoostChevron', arcM, CHEVRON_Y_OFFSET, armOffsetM, -CHEVRON_ANGLE_DEG, CHEVRON_ARM_LENGTH_M, CHEVRON_ARM_WIDTH_M)
    }
  }

  /**
   * Place one flat plane at (arc, lateral) on the track. The entity's
   * final yaw composes the local tangent (entityYawDeg) with the
   * element's own angle (chevron arms); on the straight track the
   * tangent term is 0 and the result matches the original builder.
   */
  private addPlane(
    material: pc.StandardMaterial,
    name: string,
    arcM: number,
    y: number,
    lateralM: number,
    extraYawDeg: number,
    lengthX: number,
    widthZ: number,
  ): void {
    const pose = this.projection!.pose(arcM, lateralM)
    const entity = new pc.Entity(name)
    entity.addComponent('render', { type: 'plane' })
    entity.render!.meshInstances[0].material = material
    entity.setLocalScale(lengthX, 1, widthZ)
    entity.setLocalPosition(pose.x, y, pose.z)
    entity.setLocalEulerAngles(0, entityYawDeg(pose.headingDeg) + extraYawDeg, 0)
    this.root!.addChild(entity)
  }

  private makeEmissiveMaterial(emissiveScale: number): pc.StandardMaterial {
    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(PAD_COLOR_R * 0.4, PAD_COLOR_G * 0.4, PAD_COLOR_B * 0.4)
    mat.emissive = new pc.Color(PAD_COLOR_R, PAD_COLOR_G, PAD_COLOR_B)
    mat.emissiveIntensity = PULSE_BASE_INTENSITY * emissiveScale
    mat.metalness = 0
    mat.gloss = 0.3
    mat.update()
    return mat
  }
}
