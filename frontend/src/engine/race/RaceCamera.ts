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
 * RaceCamera — rear-chase camera looking along the track's travel tangent.
 *
 * Sits a few metres behind the tracked racer along the NEGATIVE travel
 * tangent, slightly elevated, aimed forward along the tangent (the
 * classic third-person running-game framing). On the straight track the
 * tangent is constant +X, so this reproduces the original behind-on--X
 * framing exactly; on the circuit the camera swings around the ring with
 * the racer. Follows the provided pose with exponential smoothing so
 * motion is responsive but never jittery — heading is monotonic across
 * laps (no 360° wrap, see TrackProjection) so a plain lerp is safe.
 *
 * Per-frame allocation hygiene: uses module-level scratch Vec3s; no
 * `new pc.Vec3()` inside the update path.
 */
import * as pc from 'playcanvas'
import type { TrackPose } from './TrackProjection'

/** Distance behind the racer along the negative travel tangent. Pulled back so the full starting grid fits in frame. */
const CAM_BEHIND_M = 10
/** Height above ground. */
const CAM_HEIGHT_M = 4
/** Look-ahead: camera aims this far in front of the racer along the tangent. */
const CAM_LOOKAHEAD_M = 14
/** Target Y — looking slightly above ground keeps road stripes + racers in frame. */
const CAM_TARGET_Y_M = 0.8
/** Exponential smoothing factor per second. Higher = snappier. */
const CAM_FOLLOW_RATE = 4

/** Degrees → radians for the tangent trigonometry. */
const RAD_PER_DEG = Math.PI / 180

// Module-level scratch — re-used every frame, never reassigned.
const _scratchPos = new pc.Vec3()
const _scratchTarget = new pc.Vec3()

export class RaceCamera {
  private camera: pc.Entity
  private app: pc.AppBase
  private updateHandler: ((dt: number) => void) | null = null
  /** Smoothed pose — each component lerps toward the provider's pose. */
  private currentX = 0
  private currentZ = 0
  private currentHeadingDeg = 0

  /**
   * poseProvider returns the tracked racer's current centreline pose
   * (position + travel heading). It's a callback so the camera doesn't
   * need to know about RacerAvatar, the track shape, or the solo/live
   * split — RaceScene wires it to the active projection.
   */
  constructor(
    camera: pc.Entity,
    app: pc.AppBase,
    private poseProvider: () => TrackPose,
  ) {
    this.camera = camera
    this.app = app
  }

  /** Snap camera to the initial racer pose (avoids a dramatic pan on scene load). */
  activate(): void {
    const pose = this.poseProvider()
    this.currentX = pose.x
    this.currentZ = pose.z
    this.currentHeadingDeg = pose.headingDeg
    this.applyTransform()

    this.updateHandler = (dt) => this.tick(dt)
    this.app.on('update', this.updateHandler)
  }

  destroy(): void {
    if (this.updateHandler) {
      this.app.off('update', this.updateHandler)
      this.updateHandler = null
    }
  }

  private tick(dt: number): void {
    const pose = this.poseProvider()
    // Exponential smoothing: current += (target - current) * (1 - e^(-rate * dt))
    const alpha = 1 - Math.exp(-CAM_FOLLOW_RATE * dt)
    this.currentX += (pose.x - this.currentX) * alpha
    this.currentZ += (pose.z - this.currentZ) * alpha
    this.currentHeadingDeg += (pose.headingDeg - this.currentHeadingDeg) * alpha
    this.applyTransform()
  }

  private applyTransform(): void {
    // Rear-chase: camera sits on the track centreline behind the racer
    // along the negative travel tangent, aimed forward along the tangent
    // so the road ahead reads straight in screen space. Straight track:
    // heading 0 → tangent (1, 0) → the historical (x − 10, 4, 0) /
    // (x + 14, 0.8, 0) framing, unchanged.
    const headingRad = this.currentHeadingDeg * RAD_PER_DEG
    const tanX = Math.cos(headingRad)
    const tanZ = Math.sin(headingRad)
    _scratchPos.set(
      this.currentX - CAM_BEHIND_M * tanX,
      CAM_HEIGHT_M,
      this.currentZ - CAM_BEHIND_M * tanZ,
    )
    _scratchTarget.set(
      this.currentX + CAM_LOOKAHEAD_M * tanX,
      CAM_TARGET_Y_M,
      this.currentZ + CAM_LOOKAHEAD_M * tanZ,
    )
    this.camera.setPosition(_scratchPos)
    this.camera.lookAt(_scratchTarget)
  }
}
