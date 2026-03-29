/**
 * GardenRoom — stub for future shared garden multiplayer.
 *
 * Future: all users walk in the garden together, see each other,
 * see agent activity, and interact with the shared world.
 * This is a placeholder for that functionality.
 */
import { Room, Client } from "colyseus"
import { Schema, MapSchema, type } from "@colyseus/schema"
import { PlayerState } from "../schema/PlayerState"

class GardenRoomState extends Schema {
  @type({ map: PlayerState }) players = new MapSchema<PlayerState>()
}

export class GardenRoom extends Room<GardenRoomState> {
  maxClients = 50

  onCreate() {
    this.setState(new GardenRoomState())

    // Agent activity broadcast — relay to all other clients so everyone sees robots
    this.onMessage("agent_activity", (client, data: Record<string, unknown>) => {
      // Broadcast to all OTHER clients (not the sender)
      this.broadcast("agent_activity", data, { except: client })
    })

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
      const validAnims = ["idle", "walk", "sit", "sleep"]
      if (!validAnims.includes(data.animState)) return
      player.x = data.x
      player.z = data.z
      player.yaw = data.yaw
      player.animState = data.animState
    })
  }

  onJoin(client: Client, options: { userId: string; name: string }) {
    console.log(`[GardenRoom] ${options.name} joined`)
    const player = new PlayerState()
    player.userId = options.userId || client.sessionId
    player.name = options.name || "Visitor"
    player.connected = true
    this.state.players.set(client.sessionId, player)
  }

  onLeave(client: Client) {
    this.state.players.delete(client.sessionId)
  }
}
