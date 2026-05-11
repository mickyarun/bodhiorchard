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
 * CoffeeBarRemotePlayers — spawns / updates / despawns remote-player avatars
 * inside the coffee bar interior.
 *
 * Reconciles on each tick against the CoffeeBarRoomClient's player list:
 *   - New userIds → spawn a NetworkedPlayer
 *   - Known userIds → push the target position/anim into the existing entity
 *   - Vanished userIds → despawn
 *
 * The local player is filtered out by userId — `PlayerController` already
 * renders them.
 */
import type * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import { NetworkedPlayer } from '../../multiplayer/NetworkedPlayer'
import type { PlayerData } from '../../multiplayer/ColyseusClient'
import type { CoffeeBarRoomClient } from './CoffeeBarRoomClient'

export class CoffeeBarRemotePlayers {
  private byUserId = new Map<string, NetworkedPlayer>()
  /** userIds where a spawn is in-flight — prevents duplicate GLB loads. */
  private spawning = new Set<string>()

  constructor(
    private readonly root: pc.Entity,
    private readonly loader: AssetLoader,
    private readonly roomClient: CoffeeBarRoomClient,
    private readonly localUserId: string,
  ) {}

  /** Per-frame reconcile. Cheap — no allocations in the hot path. */
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

    // Despawn anyone no longer in the snapshot.
    for (const [userId, np] of this.byUserId) {
      if (!seen.has(userId)) {
        np.despawn()
        this.byUserId.delete(userId)
      }
    }

    // Interpolate existing entities toward their target.
    for (const np of this.byUserId.values()) np.update()
  }

  /** Despawn every remote player. Called on scene exit. */
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
      // A reconcile may have fired during the await; only keep this entity
      // if no other spawn for the same userId raced ahead of us.
      if (this.byUserId.has(player.userId)) {
        np.despawn()
      } else {
        this.byUserId.set(player.userId, np)
      }
    } catch (err) {
      console.warn('[CoffeeBarRemotePlayers] spawn failed for', player.userId, err)
    } finally {
      this.spawning.delete(player.userId)
    }
  }
}
