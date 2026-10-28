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
 * ColyseusClient — singleton WebSocket client for multiplayer.
 *
 * Manages connection to the Colyseus server and provides
 * join/leave helpers for house rooms.
 */
import { Client, Room } from "@colyseus/sdk"
import { resolveColyseusUrl } from "./colyseusUrl"

export interface PlayerData {
  userId: string
  name: string
  characterModel: string
  x: number
  z: number
  yaw: number
  animState: string
}

export interface MultiplayerCallbacks {
  onPlayerJoin?: (sessionId: string, player: PlayerData) => void
  onPlayerLeave?: (sessionId: string, player: PlayerData) => void
  onPlayerMove?: (sessionId: string, player: PlayerData) => void
}

/**
 * The user joining a shared room. The server verifies `token` and takes the
 * user's id, name and org from it; `userId` / `name` are display hints only.
 */
export interface RoomJoinUser {
  userId: string
  name: string
  characterModel?: string
  token: string
}

/** Shared rooms joined by their owning keys (see multiplayer/src/roomDefinitions.ts). */
type SharedRoomName = "house" | "coffeebar" | "cafeteria"

export class ColyseusClient {
  private static instance: ColyseusClient | null = null
  private client: Client
  private currentRoom: Room | null = null
  private callbacks: MultiplayerCallbacks = {}

  private constructor(serverUrl: string) {
    this.client = new Client(serverUrl)
  }

  static getInstance(serverUrl?: string): ColyseusClient {
    if (!ColyseusClient.instance) {
      ColyseusClient.instance = new ColyseusClient(serverUrl ?? resolveColyseusUrl())
    }
    return ColyseusClient.instance
  }

  /** Set callbacks for player events. */
  setCallbacks(cbs: MultiplayerCallbacks): void {
    this.callbacks = cbs
  }

  /**
   * Join a house room. One room per house owner within an org: visitors of
   * the same house share `house-{memberId}`.
   */
  async joinHouseRoom(orgId: string, memberId: string, user: RoomJoinUser): Promise<Room> {
    return this.joinSharedRoom(
      "house",
      { roomId: `house-${memberId}`, orgId, ownerId: memberId },
      user,
    )
  }

  /**
   * Join the coffee bar room. One room per org — every visitor across the org
   * joins the same `coffeebar-{orgId}` so the queue and brewing state are
   * globally consistent.
   *
   * Wires the same player join/leave/move listeners as joinHouseRoom.
   * Coffee-specific messages (enqueue, ack, leave queue) are sent via
   * sendCoffeeEnqueue / sendCoffeeAckDispense / sendCoffeeLeaveQueue.
   */
  async joinCoffeeBarRoom(orgId: string, user: RoomJoinUser): Promise<Room> {
    return this.joinSharedRoom("coffeebar", { roomId: `coffeebar-${orgId}`, orgId }, user)
  }

  /** Send a coffee order enqueue request. Server validates the drink. */
  sendCoffeeEnqueue(drink: string): void {
    this.currentRoom?.send("coffee_enqueue", { drink })
  }

  /** Drop out of the coffee queue. Ignored server-side if already active. */
  sendCoffeeLeaveQueue(): void {
    this.currentRoom?.send("coffee_leave_queue", {})
  }

  /** Ack that the drink was collected; advances dispensed -> idle immediately. */
  sendCoffeeAckDispense(): void {
    this.currentRoom?.send("coffee_ack_dispense", {})
  }

  /**
   * Join the cafeteria room. One room per org — every visitor across the org
   * joins the same `cafeteria-{orgId}` so the queue and cooking state are
   * globally consistent. Mirrors joinCoffeeBarRoom.
   */
  async joinCafeteriaRoom(orgId: string, user: RoomJoinUser): Promise<Room> {
    return this.joinSharedRoom("cafeteria", { roomId: `cafeteria-${orgId}`, orgId }, user)
  }

  /** Send a cafeteria meal enqueue request. Server validates the meal. */
  sendCafeteriaEnqueue(meal: string): void {
    this.currentRoom?.send("cafe_enqueue", { meal })
  }

  /** Drop out of the cafeteria queue. Ignored server-side if already active. */
  sendCafeteriaLeaveQueue(): void {
    this.currentRoom?.send("cafe_leave_queue", {})
  }

  /** Ack that the meal was collected; advances dispensed -> idle immediately. */
  sendCafeteriaAckDispense(): void {
    this.currentRoom?.send("cafe_ack_dispense", {})
  }

  /**
   * Join the org-wide room. One room per org holds authoritative state
   * for all members + agents. Creates `org-{orgId}` if not exists.
   *
   * Does NOT wire setupStateListeners (that's for HouseRoom only).
   * OrgRoom state subscription is handled by OrgRoomClient.
   */
  async joinOrgRoom(
    orgId: string,
    userData: { userId: string; name: string; characterModel?: string; token?: string },
  ): Promise<Room> {
    if (this.currentRoom) {
      await this.leaveRoom()
    }

    try {
      this.currentRoom = await this.client.joinOrCreate("org", {
        roomId: `org-${orgId}`,
        orgId,
        userId: userData.userId,
        name: userData.name,
        characterModel: userData.characterModel ?? '',
        token: userData.token ?? '',
      })
      return this.currentRoom
    } catch (err) {
      console.warn("[ColyseusClient] Failed to join org room:", err)
      throw err
    }
  }

  /**
   * Leave any current room, then join (or create) the shared room `name`
   * matched on `keys`, carrying the user's token for the server to verify.
   */
  private async joinSharedRoom(
    name: SharedRoomName,
    keys: Record<string, string>,
    user: RoomJoinUser,
  ): Promise<Room> {
    if (this.currentRoom) {
      await this.leaveRoom()
    }

    try {
      this.currentRoom = await this.client.joinOrCreate(name, {
        ...keys,
        userId: user.userId,
        name: user.name,
        characterModel: user.characterModel ?? '',
        token: user.token,
      })

      this.setupStateListeners()
      return this.currentRoom
    } catch (err) {
      console.warn(`[ColyseusClient] Failed to join ${name} room:`, err)
      throw err
    }
  }

  /** Leave the current room. */
  async leaveRoom(): Promise<void> {
    if (!this.currentRoom) return
    try {
      await this.currentRoom.leave()
    } catch {
      // Room may already be disconnected
    }
    this.currentRoom = null
  }

  /** Send a position update to the server. */
  sendMove(x: number, z: number, yaw: number, animState: string): void {
    this.currentRoom?.send("move", { x, z, yaw, animState })
  }

  /** Forward an agent activity event to all players in the room. */
  sendAgentActivity(data: Record<string, unknown>): void {
    this.currentRoom?.send("agent_activity", data)
  }

  /** Set callback for remote agent activity events from other players. */
  onAgentActivity: ((data: Record<string, unknown>) => void) | null = null

  get room(): Room | null { return this.currentRoom }
  get sessionId(): string | undefined { return this.currentRoom?.sessionId }

  private setupStateListeners(): void {
    if (!this.currentRoom) return

    // Listen for agent activity broadcasts from other players
    this.currentRoom.onMessage("agent_activity", (data: Record<string, unknown>) => {
      this.onAgentActivity?.(data)
    })

    // Use onStateChange for broad state sync — simpler than per-field listeners.
    // The room state has a `players` MapSchema. We track known sessions to detect joins/leaves.
    const knownSessions = new Set<string>()

    this.currentRoom.onStateChange((state: Record<string, unknown>) => {
      const players = state.players as Map<string, PlayerData> | undefined
      if (!players) return

      // Detect joins and moves
      players.forEach((player: PlayerData, sessionId: string) => {
        if (sessionId === this.currentRoom?.sessionId) return
        if (!knownSessions.has(sessionId)) {
          knownSessions.add(sessionId)
          this.callbacks.onPlayerJoin?.(sessionId, player)
        } else {
          this.callbacks.onPlayerMove?.(sessionId, player)
        }
      })

      // Detect leaves
      for (const sid of knownSessions) {
        if (!players.has(sid)) {
          knownSessions.delete(sid)
          this.callbacks.onPlayerLeave?.(sid, { userId: '', name: '', characterModel: '', x: 0, z: 0, yaw: 0, animState: 'idle' })
        }
      }
    })
  }

  static destroy(): void {
    ColyseusClient.instance?.leaveRoom().catch(() => {
      // Socket may already be closed — safe to ignore
    })
    ColyseusClient.instance = null
  }
}
