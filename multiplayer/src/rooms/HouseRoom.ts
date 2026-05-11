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
 * HouseRoom — Colyseus room for house interior multiplayer.
 *
 * Room ID pattern: "house-{memberId}"
 * Each house is a separate room. Players joining the same house
 * see each other's avatars with synced position/animation.
 *
 * Messages:
 *   "move" → { x, z, yaw, animState } — player position update (~20Hz)
 */
import { Room, Client } from "colyseus"
import { Schema, MapSchema, type } from "@colyseus/schema"
import { PlayerState } from "../schema/PlayerState"

class HouseRoomState extends Schema {
  @type({ map: PlayerState }) players = new MapSchema<PlayerState>()
  @type("string") ownerId: string = ""  // whose house this is
}

export class HouseRoom extends Room<{ state: HouseRoomState }> {
  maxClients = 10

  onCreate(options: { ownerId?: string }) {
    this.setState(new HouseRoomState())
    if (options.ownerId) {
      this.state.ownerId = options.ownerId
    }

    // Handle position updates with server-side validation
    this.onMessage("move", (client, data: {
      x: number
      z: number
      yaw: number
      animState: string
    }) => {
      const player = this.state.players.get(client.sessionId)
      if (!player) return
      if (typeof data.x !== "number" || !isFinite(data.x)) return
      if (typeof data.z !== "number" || !isFinite(data.z)) return
      if (typeof data.yaw !== "number" || !isFinite(data.yaw)) return
      const validAnims = ["idle", "walk", "sit", "sleep", "brew", "drink"]
      if (!validAnims.includes(data.animState)) return
      player.x = data.x
      player.z = data.z
      player.yaw = data.yaw
      player.animState = data.animState
    })
  }

  onJoin(client: Client, options: { userId: string; name: string; characterModel?: string }) {
    console.log(`[HouseRoom] ${options.name} (${client.sessionId}) joined`)
    const player = new PlayerState()
    player.userId = options.userId || client.sessionId
    player.name = options.name || "Visitor"
    player.characterModel = options.characterModel || ""
    player.connected = true
    this.state.players.set(client.sessionId, player)
  }

  onLeave(client: Client) {
    const player = this.state.players.get(client.sessionId)
    console.log(`[HouseRoom] ${player?.name || client.sessionId} left`)
    this.state.players.delete(client.sessionId)
  }

  onDispose() {
    console.log(`[HouseRoom] Room ${this.roomId} disposed`)
  }
}
