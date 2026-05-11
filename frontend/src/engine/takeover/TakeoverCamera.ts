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
 * TakeoverCamera — third-person orbit camera for garden takeover mode.
 *
 * Same pattern as InteriorCamera but with garden-appropriate presets:
 * lower angle, wider distance, more zoom range for outdoor feel.
 *
 * Shares the same pc.Entity camera as CameraController.
 * Only one should be enabled at a time (mutual exclusion via sceneState).
 */
import * as pc from 'playcanvas'
import { OrbitCamera } from '../housetest/OrbitCamera'

const GARDEN_YAW   = 0
const GARDEN_PITCH  = 50   // top-down-ish angle — keeps character visible with surrounding context
const GARDEN_DIST   = 12   // wider view of garden surroundings

export class TakeoverCamera {
  private orbit: OrbitCamera
  private active = false

  constructor() {
    this.orbit = new OrbitCamera()
  }

  /** Current yaw in degrees — used by TakeoverController for camera-relative WASD. */
  get yaw(): number { return this.orbit.yaw }

  get isActive(): boolean { return this.active }

  /**
   * Enable takeover camera — attaches mouse listeners and takes over the camera entity.
   */
  enable(cameraEntity: pc.Entity, canvas: HTMLCanvasElement): void {
    if (this.active) return
    this.orbit.init(canvas, cameraEntity, GARDEN_YAW, GARDEN_PITCH, GARDEN_DIST)
    this.active = true
  }

  /** Disable takeover camera — removes all event listeners. */
  disable(): void {
    if (!this.active) return
    this.orbit.destroy()
    this.active = false
  }

  /** Per-frame update — positions camera on orbit sphere around player. */
  update(playerPos: pc.Vec3): void {
    if (!this.active) return
    this.orbit.update(playerPos)
  }

  destroy(): void {
    this.disable()
  }
}
