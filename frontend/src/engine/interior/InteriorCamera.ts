// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
