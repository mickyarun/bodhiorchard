// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * PlayerSyncAdapter — throttled position broadcaster.
 *
 * Sends player position to Colyseus at ~20Hz (every 50ms),
 * decoupled from the render frame rate. Only sends when
 * position or animation state has changed.
 */
import type { ColyseusClient } from './ColyseusClient'

const SEND_INTERVAL_MS = 50  // 20Hz

export class PlayerSyncAdapter {
  private lastSendTime = 0
  private lastX = NaN
  private lastZ = NaN
  private lastYaw = NaN
  private lastAnim = ''

  /**
   * Call each frame. Sends position update if enough time has passed
   * and the position/animation has changed.
   */
  update(
    dt: number,
    x: number,
    z: number,
    yaw: number,
    animState: string,
    client: ColyseusClient,
  ): void {
    this.lastSendTime += dt * 1000
    if (this.lastSendTime < SEND_INTERVAL_MS) return
    this.lastSendTime = 0

    // Skip if nothing changed (avoid unnecessary network traffic)
    if (x === this.lastX && z === this.lastZ &&
        yaw === this.lastYaw && animState === this.lastAnim) {
      return
    }

    this.lastX = x
    this.lastZ = z
    this.lastYaw = yaw
    this.lastAnim = animState
    client.sendMove(x, z, yaw, animState)
  }

  reset(): void {
    this.lastSendTime = 0
    this.lastX = NaN
    this.lastZ = NaN
    this.lastYaw = NaN
    this.lastAnim = ''
  }
}
