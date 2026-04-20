// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CafeteriaRemotePlayers — spawns / updates / despawns remote-player avatars
 * inside the cafeteria interior. Mirrors CoffeeBarRemotePlayers verbatim;
 * the only difference is the RoomClient type it reads from.
 */
import type * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import { NetworkedPlayer } from '../../multiplayer/NetworkedPlayer'
import type { PlayerData } from '../../multiplayer/ColyseusClient'
import type { CafeteriaRoomClient } from './CafeteriaRoomClient'

export class CafeteriaRemotePlayers {
  private byUserId = new Map<string, NetworkedPlayer>()
  private spawning = new Set<string>()

  constructor(
    private readonly root: pc.Entity,
    private readonly loader: AssetLoader,
    private readonly roomClient: CafeteriaRoomClient,
    private readonly localUserId: string,
  ) {}

  update(): void {
    const snapshot = this.roomClient.getPlayers()
    const seen = new Set<string>()

    for (const player of snapshot) {
      if (!player.userId || player.userId === this.localUserId) continue
      seen.add(player.userId)

      const existing = this.byUserId.get(player.userId)
      if (existing) {
        existing.setTarget(player)
      } else if (!this.spawning.has(player.userId)) {
        this.spawnRemote(player)
      }
    }

    for (const [userId, np] of this.byUserId) {
      if (!seen.has(userId)) {
        np.despawn()
        this.byUserId.delete(userId)
      }
    }

    for (const np of this.byUserId.values()) np.update()
  }

  destroy(): void {
    for (const np of this.byUserId.values()) np.despawn()
    this.byUserId.clear()
    this.spawning.clear()
  }

  private async spawnRemote(player: PlayerData): Promise<void> {
    this.spawning.add(player.userId)
    try {
      const np = new NetworkedPlayer(player.userId, player.name || 'Visitor')
      await np.spawn(this.root, this.loader, player)
      if (this.byUserId.has(player.userId)) {
        np.despawn()
      } else {
        this.byUserId.set(player.userId, np)
      }
    } catch (err) {
      console.warn('[CafeteriaRemotePlayers] spawn failed for', player.userId, err)
    } finally {
      this.spawning.delete(player.userId)
    }
  }
}
