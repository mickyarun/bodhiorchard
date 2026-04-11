/**
 * ColyseusClient — singleton WebSocket client for multiplayer.
 *
 * Manages connection to the Colyseus server and provides
 * join/leave helpers for house rooms.
 */
import { Client, Room } from "@colyseus/sdk"

const DEFAULT_SERVER = "ws://localhost:2567"

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

export class ColyseusClient {
  private static instance: ColyseusClient | null = null
  private client: Client
  private currentRoom: Room | null = null
  private callbacks: MultiplayerCallbacks = {}

  private constructor(serverUrl: string) {
    this.client = new Client(serverUrl)
  }

  static getInstance(serverUrl = DEFAULT_SERVER): ColyseusClient {
    if (!ColyseusClient.instance) {
      ColyseusClient.instance = new ColyseusClient(serverUrl)
    }
    return ColyseusClient.instance
  }

  /** Set callbacks for player events. */
  setCallbacks(cbs: MultiplayerCallbacks): void {
    this.callbacks = cbs
  }

  /** Join a house room. Creates or joins "house-{memberId}". */
  async joinHouseRoom(
    memberId: string,
    userData: { userId: string; name: string; characterModel?: string },
  ): Promise<Room> {
    if (this.currentRoom) {
      await this.leaveRoom()
    }

    try {
      this.currentRoom = await this.client.joinOrCreate("house", {
        roomId: `house-${memberId}`,
        ownerId: memberId,
        userId: userData.userId,
        name: userData.name,
        characterModel: userData.characterModel ?? '',
      })

      this.setupStateListeners()
      return this.currentRoom
    } catch (err) {
      console.warn("[ColyseusClient] Failed to join house room:", err)
      throw err
    }
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
