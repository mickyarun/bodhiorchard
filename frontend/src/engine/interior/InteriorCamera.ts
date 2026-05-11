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
 * InteriorCamera — enable/disable wrapper around housetest OrbitCamera.
 *
 * Shares the same pc.Entity camera as CameraController.
 * Only one should be enabled at a time (mutual exclusion via sceneState).
 *
 * Interior preset: yaw=0, pitch=60°, distance=6 — elevated view
 * showing the full room from above.
 */
import * as pc from 'playcanvas'
import { OrbitCamera } from '../housetest/OrbitCamera'

// Interior camera defaults — elevated angle to show the small room
const INT_YAW = 0
const INT_PITCH = 60
const INT_DIST = 6

export class InteriorCamera {
  private orbit: OrbitCamera
  private active = false

  constructor() {
    this.orbit = new OrbitCamera()
  }

  /** Current yaw in degrees — used by PlayerController for camera-relative WASD. */
  get yaw(): number { return this.orbit.yaw }

  get isActive(): boolean { return this.active }

  /**
   * Enable interior camera — attaches mouse listeners and takes over the camera entity.
   * Must be called during a black-frame transition (SceneTransition.perform callback).
   */
  enable(cameraEntity: pc.Entity, canvas: HTMLCanvasElement): void {
    if (this.active) return
    this.orbit.init(canvas, cameraEntity, INT_YAW, INT_PITCH, INT_DIST)
    this.active = true
  }

  /** Disable interior camera — removes all event listeners. */
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

  /** Snap to a specific view without animation. */
  setView(yaw: number, pitch: number, distance: number): void {
    this.orbit.setView(yaw, pitch, distance)
  }

  destroy(): void {
    this.disable()
  }
}
