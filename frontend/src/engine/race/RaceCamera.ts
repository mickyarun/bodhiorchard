// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar
/**
 * RaceCamera — rear-chase camera looking down the track along +X.
 *
 * Sits a few metres behind the leader, slightly elevated, aimed forward
 * so the road reads as a straight line into the distance (the classic
 * third-person running-game framing). Follows the leader with
 * exponential smoothing so motion is responsive but never jittery.
 *
 * Per-frame allocation hygiene: uses module-level scratch Vec3s; no
 * `new pc.Vec3()` inside the update path.
 */
import * as pc from 'playcanvas'

/** Distance behind the leader along -X. Pulled back so the full starting grid fits in frame. */
const CAM_BEHIND_M = 10
/** Height above ground. */
const CAM_HEIGHT_M = 4
/** Look-ahead: camera aims this far in front of the leader. */
const CAM_LOOKAHEAD_M = 14
/** Target Y — looking slightly above ground keeps road stripes + racers in frame. */
const CAM_TARGET_Y_M = 0.8
/** Exponential smoothing factor per second. Higher = snappier. */
const CAM_FOLLOW_RATE = 4

// Module-level scratch — re-used every frame, never reassigned.
const _scratchPos = new pc.Vec3()
const _scratchTarget = new pc.Vec3()

export class RaceCamera {
  private camera: pc.Entity
  private app: pc.AppBase
  private updateHandler: ((dt: number) => void) | null = null
  private leaderX = 0
  /** Smoothed X — lerps toward leaderX each frame. */
  private currentX = 0

  /**
   * leaderProvider returns the current lead racer's X position in metres.
   * It's a callback so the camera doesn't need to know about RacerAvatar
   * or the solo/live split.
   */
  constructor(
    camera: pc.Entity,
    app: pc.AppBase,
    private leaderProvider: () => number,
  ) {
    this.camera = camera
    this.app = app
  }

  /** Snap camera to the initial leader position (avoids a dramatic pan on scene load). */
  activate(): void {
    this.leaderX = this.leaderProvider()
    this.currentX = this.leaderX
    this.applyTransform(this.currentX)

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
    this.leaderX = this.leaderProvider()
    // Exponential smoothing: currentX += (target - current) * (1 - e^(-rate * dt))
    const alpha = 1 - Math.exp(-CAM_FOLLOW_RATE * dt)
    this.currentX += (this.leaderX - this.currentX) * alpha
    this.applyTransform(this.currentX)
  }

  private applyTransform(x: number): void {
    // Rear-chase: camera sits on the track centreline, behind the leader,
    // aimed forward along +X so the road appears straight in screen space.
    _scratchPos.set(x - CAM_BEHIND_M, CAM_HEIGHT_M, 0)
    _scratchTarget.set(x + CAM_LOOKAHEAD_M, CAM_TARGET_Y_M, 0)
    this.camera.setPosition(_scratchPos)
    this.camera.lookAt(_scratchTarget)
  }
}
