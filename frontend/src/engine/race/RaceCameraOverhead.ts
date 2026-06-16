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
 * RaceCameraOverhead — dynamic pack-framing spectator camera.
 *
 * A static bird's-eye sized to the whole track left the racers as tiny dots.
 * Instead this camera frames the PACK: each frame it centres on the racers'
 * bounding box and picks a height that fits them (zooming in when bunched,
 * out as they spread), so the runners stay as large as the action allows. The
 * centre + zoom are exponentially smoothed for a gentle spectator pan, and a
 * fixed oblique pull-back keeps depth readable (never pure straight-down, which
 * also avoids the degenerate lookAt up-vector case).
 *
 * Per-frame allocation hygiene: module-level scratch Vec3s; no `new` in tick.
 */
import * as pc from 'playcanvas'

/** Vertical FOV in degrees. */
const CAM_FOV_DEG = 40
/** Ground Y the camera aims at — the track surface. */
const CAM_TARGET_Y_M = 0
/** Metres of slack kept around the pack so racers never sit at the frame edge. */
const FRAME_MARGIN_M = 12
/** Closest the camera comes (m) — stops it diving in when the pack is bunched (the start grid). */
const MIN_HEIGHT_M = 30
/** Farthest the camera pulls back (m) — caps zoom-out when the field is strung out. */
const MAX_HEIGHT_M = 95
/** Oblique pull-back as a fraction of height (≈ -76° pitch) for a depth cue. */
const OBLIQUE_RATIO = 0.25
/** Exponential smoothing rate (per second). Gentle, so spectating reads as a calm pan. */
const FOLLOW_RATE = 2.5

const _pos = new pc.Vec3()
const _target = new pc.Vec3()

/** The pack's framing: centre on the ground plane + the larger XZ spread. */
export interface PackFraming {
  x: number
  z: number
  spreadM: number
}

export interface RaceCameraOverheadOptions {
  /** Returns the current pack framing, or null when there are no racers to frame. */
  framingProvider: () => PackFraming | null
  /** Fallback centre (course midpoint) used before any framing is available. */
  fallbackCenter: { x: number; z: number }
}

export class RaceCameraOverhead {
  private camera: pc.Entity
  private app: pc.AppBase
  private opts: RaceCameraOverheadOptions
  private updateHandler: ((dt: number) => void) | null = null
  private readonly halfFovRad = (CAM_FOV_DEG / 2) * (Math.PI / 180)
  // Smoothed framing state.
  private curX = 0
  private curZ = 0
  private curHeight = MAX_HEIGHT_M

  constructor(camera: pc.Entity, app: pc.AppBase, opts: RaceCameraOverheadOptions) {
    this.camera = camera
    this.app = app
    this.opts = opts
  }

  activate(): void {
    const cam = this.camera.camera
    if (cam) cam.fov = CAM_FOV_DEG

    const target = this.resolveTarget()
    this.curX = target.x
    this.curZ = target.z
    this.curHeight = target.height
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
    const target = this.resolveTarget()
    const alpha = 1 - Math.exp(-FOLLOW_RATE * dt)
    this.curX += (target.x - this.curX) * alpha
    this.curZ += (target.z - this.curZ) * alpha
    this.curHeight += (target.height - this.curHeight) * alpha
    this.applyTransform()
  }

  /** Centre + height that frames the current pack (clamped), or the fallback. */
  private resolveTarget(): { x: number; z: number; height: number } {
    const framing = this.opts.framingProvider()
    if (framing === null) {
      return { x: this.opts.fallbackCenter.x, z: this.opts.fallbackCenter.z, height: MAX_HEIGHT_M }
    }
    // Height that fits the half-spread (plus margin) in the vertical FOV; the
    // wider horizontal FOV then comfortably covers the other axis.
    const desired = (framing.spreadM / 2 + FRAME_MARGIN_M) / Math.tan(this.halfFovRad)
    const height = Math.min(MAX_HEIGHT_M, Math.max(MIN_HEIGHT_M, desired))
    return { x: framing.x, z: framing.z, height }
  }

  private applyTransform(): void {
    _pos.set(this.curX - this.curHeight * OBLIQUE_RATIO, this.curHeight, this.curZ)
    _target.set(this.curX, CAM_TARGET_Y_M, this.curZ)
    this.camera.setPosition(_pos)
    this.camera.lookAt(_target)
  }
}
