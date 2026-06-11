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
 * RaceCameraOverhead — fixed-position spectator camera.
 *
 * Unlike `RaceCamera` (which trails the leader), this camera never moves
 * after activation: spectators should see all racers at once so they can
 * follow the pack, not just the leader. Positioned high above the track
 * midpoint and angled steeply down, with its FOV tuned so a full 200 m
 * 10-lane track fits inside a 16:9 viewport with generous margin.
 *
 * No per-frame work — `activate()` sets the transform once and the PlayCanvas
 * update loop never touches this camera again. `destroy()` exists only for
 * symmetry with `RaceCamera` so the scene's teardown code is uniform.
 */
import * as pc from 'playcanvas'
import { loopBounds } from '@shared/race/LoopPath'
import { LOOP_LENGTH_M } from '@shared/race/RaceConstants'
import type { TrackShape } from '@shared/race/types'

/**
 * Pitch (degrees) — straight down is -90, horizon is 0. At -80 the ground
 * plane reads as a gentle oblique (not pure top-down) so depth still reads.
 */
const CAM_PITCH_DEG = -80

/**
 * Height above the ground plane in metres. Tuned so a 200 m × 15 m track
 * fits inside a 16:9 viewport with the FOV below — leave margin for HUD.
 */
const CAM_HEIGHT_M = 70

/**
 * Camera offset from the midpoint along -X. A small pull-back stops the
 * near edge of the track from clipping the camera and gives spectators a
 * slight "looking-down-the-straight" sense of direction.
 */
const CAM_BEHIND_MIDPOINT_M = 12

/**
 * Vertical FOV in degrees. 40° + 70 m height frames a 200 m track without
 * the racers dropping below 6px at full-HD; tighter than this and 10-lane
 * 200 m races start to crop on narrow viewports.
 */
const CAM_FOV_DEG = 40

/** Ground Y the camera is pointed at. Zero puts the focus on the track surface. */
const CAM_TARGET_Y_M = 0

/**
 * Extra metres of grass kept visible beyond the circuit's outer edge so
 * the ring never kisses the viewport border.
 */
const CIRCUIT_FIT_MARGIN_M = 8

export interface RaceCameraOverheadOptions {
  /** Race distance in metres — straight midpoint X, or circuit circumference. */
  distanceM: number
  /** Road width in metres — sizes the circuit fit; unused for straight. */
  trackWidthM: number
  /** Track layout — picks the straight-midpoint or circuit-centre framing. */
  trackShape: TrackShape
}

export class RaceCameraOverhead {
  private camera: pc.Entity
  private opts: RaceCameraOverheadOptions

  constructor(camera: pc.Entity, opts: RaceCameraOverheadOptions) {
    this.camera = camera
    this.opts = opts
  }

  /**
   * Place the camera at its fixed viewpoint. Called once by `RaceScene`
   * when the spectator path is taken. No update subscription — the
   * transform never changes after this call.
   */
  activate(): void {
    const cam = this.camera.camera
    if (cam) cam.fov = CAM_FOV_DEG

    if (this.opts.trackShape === 'circuit') {
      this.activateCircuit()
      return
    }

    const midpointX = this.opts.distanceM / 2
    this.camera.setPosition(midpointX - CAM_BEHIND_MIDPOINT_M, CAM_HEIGHT_M, 0)
    this.camera.setLocalEulerAngles(CAM_PITCH_DEG, 0, 0)
    // `setLocalEulerAngles` alone gets the pitch right but we want the camera
    // facing toward +X (finish direction). Re-orient by looking at a point
    // a bit past the midpoint at ground level.
    this.camera.lookAt(midpointX, CAM_TARGET_Y_M, 0)
  }

  /**
   * Circuit framing: hover over the centre of the loop's bounding box —
   * the organic loop isn't symmetric, so the centre comes from LoopPath's
   * bounds rather than a circle radius — at a height where the larger
   * box half-extent (plus road width and a grass margin) fits the
   * vertical FOV: height = halfExtent / tan(fov / 2). Sizing to the
   * larger axis keeps the whole course on screen even in a square
   * viewport. The same small -X pull-back as the straight path keeps the
   * view obliquely angled (and keeps lookAt away from the degenerate
   * straight-down up-vector case).
   */
  private activateCircuit(): void {
    // Frame the fixed physical loop (LOOP_LENGTH_M), not the race distance —
    // a 1-lap and 2-lap race share the same-sized course.
    const bounds = loopBounds(LOOP_LENGTH_M)
    const centerX = (bounds.minX + bounds.maxX) / 2
    const centerZ = (bounds.minZ + bounds.maxZ) / 2
    const halfSpanM = Math.max(bounds.maxX - bounds.minX, bounds.maxZ - bounds.minZ) / 2
    const halfExtentM = halfSpanM + this.opts.trackWidthM / 2 + CIRCUIT_FIT_MARGIN_M
    const halfFovRad = (CAM_FOV_DEG / 2) * (Math.PI / 180)
    const heightM = halfExtentM / Math.tan(halfFovRad)

    this.camera.setPosition(centerX - CAM_BEHIND_MIDPOINT_M, heightM, centerZ)
    this.camera.lookAt(centerX, CAM_TARGET_Y_M, centerZ)
  }

  destroy(): void {
    // Intentional no-op — no listeners, no allocations. Present for API
    // symmetry with `RaceCamera` so `RaceScene.destroy()` can call both
    // without branching on camera type.
  }
}
