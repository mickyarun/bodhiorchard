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
 * GraphCameraController — orbit camera with smooth focus transitions.
 *
 * Owns all camera state: yaw, pitch, distance, target, auto-rotation,
 * and animated transitions. The GraphEngine delegates camera concerns here.
 */
import * as pc from 'playcanvas'
import type { InputManager } from '../input/InputManager'

// ─── Animation State ─────────────────────────────

interface CameraSnapshot {
  targetX: number
  targetY: number
  targetZ: number
  distance: number
  pitch: number
}

// ─── Controller ──────────────────────────────────

export class GraphCameraController {
  private entity: pc.Entity

  // Orbit state
  private yaw = 0
  private pitch = 30
  private distance = 60
  private target = new pc.Vec3(0, 0, 0)

  // Auto-rotation
  private rotationSpeed = 5

  // Smooth focus animation
  private animating = false
  private animProgress = 0
  private animDuration = 0.6
  private animFrom: CameraSnapshot = { targetX: 0, targetY: 0, targetZ: 0, distance: 60, pitch: 10 }
  private animTo: CameraSnapshot = { targetX: 0, targetY: 0, targetZ: 0, distance: 30, pitch: 20 }

  // Saved full-graph view for resetView()
  private fullViewDistance = 60
  private fullViewPitch = 10

  constructor(parent: pc.Entity) {
    this.entity = new pc.Entity('GraphCamera')
    this.entity.addComponent('camera', {
      clearColor: new pc.Color(0.06, 0.07, 0.1),
      projection: pc.PROJECTION_PERSPECTIVE,
      fov: 45,
      nearClip: 0.1,
      farClip: 1000,
      frustumCulling: true,
    })
    // v2.17+: toneMapping & gammaCorrection moved from Scene to CameraComponent
    const cam = this.entity.camera!
    ;(cam as unknown as Record<string, unknown>).toneMapping = pc.TONEMAP_ACES
    ;(cam as unknown as Record<string, unknown>).gammaCorrection = pc.GAMMA_SRGB
    parent.addChild(this.entity)
    this.applyOrbit()
  }

  /** The PlayCanvas camera entity (needed by picking and labels). */
  getEntity(): pc.Entity {
    return this.entity
  }

  /** Half-FOV in radians (used for auto-framing calculations). */
  get halfFovRad(): number {
    return ((45 / 2) * Math.PI) / 180
  }

  /** Per-frame update: animation, auto-rotation, input handling. */
  update(dt: number, input: InputManager | null): boolean {
    let changed = false

    // Smooth focus/reset animation
    if (this.animating) {
      this.animProgress += dt / this.animDuration
      const t = this.easeOutCubic(Math.min(this.animProgress, 1))

      this.target.set(
        this.animFrom.targetX + (this.animTo.targetX - this.animFrom.targetX) * t,
        this.animFrom.targetY + (this.animTo.targetY - this.animFrom.targetY) * t,
        this.animFrom.targetZ + (this.animTo.targetZ - this.animFrom.targetZ) * t,
      )
      this.distance = this.animFrom.distance + (this.animTo.distance - this.animFrom.distance) * t
      this.pitch = this.animFrom.pitch + (this.animTo.pitch - this.animFrom.pitch) * t
      changed = true

      if (this.animProgress >= 1) this.animating = false
    }

    // Auto-rotation (paused during animation)
    if (this.rotationSpeed > 0 && !this.animating) {
      this.yaw += this.rotationSpeed * dt
      changed = true
    }

    // Input: drag orbit + scroll zoom
    if (input) {
      const orbit = input.getOrbitDelta()
      if (orbit.dx !== 0 || orbit.dy !== 0) {
        this.yaw -= orbit.dx * 0.3
        this.pitch = Math.max(5, Math.min(85, this.pitch + orbit.dy * 0.3))
        changed = true
      }

      const scroll = input.getScrollDelta()
      if (scroll !== 0) {
        this.distance = Math.max(10, Math.min(300, this.distance - scroll * 3))
        changed = true
      }

      // Consume unused pan delta
      input.getPanDelta()
    }

    if (changed) this.applyOrbit()
    return changed
  }

  /** Animate camera to focus on a position at a given distance and pitch. */
  focusOn(x: number, y: number, z: number, distance: number, pitch: number): void {
    this.animFrom = {
      targetX: this.target.x,
      targetY: this.target.y,
      targetZ: this.target.z,
      distance: this.distance,
      pitch: this.pitch,
    }
    this.animTo = { targetX: x, targetY: y, targetZ: z, distance, pitch }
    this.animProgress = 0
    this.animating = true
  }

  /** Animate camera back to the full-graph overview. */
  resetView(): void {
    this.focusOn(0, 0, 0, this.fullViewDistance, this.fullViewPitch)
  }

  /** Set the distance/pitch for the full-graph overview (called after layout). */
  setFullView(distance: number, pitch: number): void {
    this.distance = distance
    this.pitch = pitch
    this.yaw = 0
    this.target.set(0, 0, 0)
    this.fullViewDistance = distance
    this.fullViewPitch = pitch
    this.applyOrbit()
  }

  // ─── Private ───────────────────────────────────

  private applyOrbit(): void {
    const pitchRad = (this.pitch * Math.PI) / 180
    const yawRad = (this.yaw * Math.PI) / 180
    const x = this.target.x + this.distance * Math.cos(pitchRad) * Math.sin(yawRad)
    const y = this.target.y + this.distance * Math.sin(pitchRad)
    const z = this.target.z + this.distance * Math.cos(pitchRad) * Math.cos(yawRad)
    this.entity.setPosition(x, y, z)
    this.entity.lookAt(this.target)
  }

  private easeOutCubic(t: number): number {
    return 1 - Math.pow(1 - t, 3)
  }
}
