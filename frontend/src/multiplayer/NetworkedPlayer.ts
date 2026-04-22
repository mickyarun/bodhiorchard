// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * NetworkedPlayer — remote player avatar for multiplayer.
 *
 * Spawns a KayKit character entity for each remote player, interpolates
 * position updates, and shows a name label. All characters are KayKit —
 * the legacy Kenney Blocky path was removed when character handling was
 * unified.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../engine/assets/AssetLoader'
import type { PlayerData } from './ColyseusClient'
import { parseCharacterModel } from '../engine/characters/CharacterConfig'
import { KayKitCharacterFactory } from '../engine/characters/KayKitCharacterFactory'

const LERP_FACTOR = 0.15  // position interpolation per frame

export class NetworkedPlayer {
  private entity: pc.Entity | null = null
  private targetX = 0
  private targetZ = 0
  private targetYaw = 0
  private seated = false

  readonly sessionId: string
  readonly name: string

  constructor(sessionId: string, name: string) {
    this.sessionId = sessionId
    this.name = name
  }

  /** Spawn the character entity under a parent (interiorRoot). */
  async spawn(
    parent: pc.Entity,
    loader: AssetLoader,
    initial: PlayerData,
    kayKitFactory?: KayKitCharacterFactory,
  ): Promise<void> {
    const config = parseCharacterModel(initial.characterModel || null)
    const seated = initial.animState === 'sit' || initial.animState === 'sleep'

    const factory = kayKitFactory ?? new KayKitCharacterFactory(loader)
    const result = await factory.create(
      initial.userId, this.name, config,
      initial.x, 0, initial.z,
      initial.yaw, seated,
    )
    parent.addChild(result.entity)
    this.entity = result.entity

    this.targetX = initial.x
    this.targetZ = initial.z
    this.targetYaw = initial.yaw
    this.seated = seated
  }

  /** Update target position and pose from network data. */
  setTarget(player: PlayerData): void {
    this.targetX = player.x
    this.targetZ = player.z
    this.targetYaw = player.yaw
    this.seated = player.animState === 'sit' || player.animState === 'sleep'
    // Apply pose transitions (sit/sleep/idle/walk) — server is authoritative.
    const anim = this.entity?.anim
    if (anim) {
      anim.setBoolean('sitting', this.seated)
    }
  }

  /** Per-frame interpolation toward target position. */
  update(): void {
    if (!this.entity) return

    // Seated NPCs snap to exact position+yaw (no drift from interpolation).
    // Walking NPCs interpolate smoothly with shortest-path yaw.
    if (this.seated) {
      this.entity.setPosition(this.targetX, 0, this.targetZ)
      this.entity.setEulerAngles(0, this.targetYaw, 0)
      return
    }

    const pos = this.entity.getPosition()
    const x = pos.x + (this.targetX - pos.x) * LERP_FACTOR
    const z = pos.z + (this.targetZ - pos.z) * LERP_FACTOR
    this.entity.setPosition(x, 0, z)

    // Shortest-path yaw interpolation: normalize delta to [-180, 180] so
    // the LERP takes the short arc (e.g., 350→10 goes +20, not −340).
    const current = this.entity.getEulerAngles().y
    let delta = this.targetYaw - current
    delta = delta - Math.round(delta / 360) * 360  // normalize to [-180, 180]
    this.entity.setEulerAngles(0, current + delta * LERP_FACTOR, 0)
  }

  despawn(): void {
    this.entity?.destroy()
    this.entity = null
  }
}
