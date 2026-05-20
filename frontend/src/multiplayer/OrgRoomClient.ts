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
 * OrgRoomClient — higher-level wrapper around Colyseus OrgRoom.
 *
 * Subscribes to server state changes and emits callbacks for:
 *   - Member add/update/remove (CharacterSystem renders these)
 *   - Agent add/update/remove (AgentCharacterSystem renders these)
 *
 * Also handles sending takeover messages and player move updates.
 *
 * Usage:
 *   const client = OrgRoomClient.getInstance()
 *   await client.connect(orgId, { userId, name, characterModel })
 *   client.onMemberAdd = (id, data) => characterSystem.spawnCharacter(data)
 *   client.onMemberUpdate = (id, data) => characterSystem.updateCharacter(data)
 *   client.onMemberRemove = (id) => characterSystem.removeCharacter(id)
 */
import { Client, getStateCallbacks, Room } from "@colyseus/sdk"
import { resolveColyseusUrl } from "./colyseusUrl"

/** Read-only snapshot of a member's state (mirrors server MemberState schema). */
export interface MemberStateSnapshot {
  userId: string
  name: string
  characterModel: string
  level: number
  levelName: string
  presence: string
  x: number
  y: number
  z: number
  yaw: number
  animState: string
  labelName: string
  labelMessage: string
  takeoverSessionId: string
  locationContext: string
  vehicleId: string
  houseLevel: number
}

/** Read-only snapshot of an agent's state (mirrors server AgentState schema). */
export interface AgentStateSnapshot {
  agentId: string
  skillSlug: string
  skillName: string
  actorName: string
  repoName: string
  budNumber: number
  x: number
  y: number
  z: number
  yaw: number
  state: string
  action: string
  message: string
}

/** Fields on the raw Colyseus schema member that we care about. */
interface RawMember {
  userId?: string
  name?: string
  characterModel?: string
  level?: number
  levelName?: string
  presence?: string
  x?: number
  y?: number
  z?: number
  yaw?: number
  animState?: string
  labelName?: string
  labelMessage?: string
  takeoverSessionId?: string
  locationContext?: string
  vehicleId?: string
  houseLevel?: number
}

/** Summary of one active race — mirrors server ActiveRaceSummary schema. */
export interface ActiveRaceSummary {
  roomId: string
  hostUserId: string
  hostName: string
  distanceM: number
  phase: string
  racerCount: number
  /** Host + invitees. Consumers filter their own id out to avoid self-watch. */
  participantUserIds: readonly string[]
}

interface RawActiveRace {
  roomId?: string
  hostUserId?: string
  hostName?: string
  distanceM?: number
  phase?: string
  racerCount?: number
  participantUserIds?: ArrayLike<string>
}

/** How long to wait for `race_created` / `race_create_failed` before giving up. */
const RACE_CREATE_TIMEOUT_MS = 5_000

interface RawAgent {
  agentId?: string
  skillSlug?: string
  skillName?: string
  actorName?: string
  repoName?: string
  budNumber?: number
  x?: number
  y?: number
  z?: number
  yaw?: number
  state?: string
  action?: string
  message?: string
}

/** Listener for any member state change (add, update, remove). */
export type MemberChangeListener = (
  userId: string,
  snapshot: MemberStateSnapshot | null,
) => void

/** Connection lifecycle states surfaced to the UI for banner rendering. */
export type ConnectionStatus =
  | "disconnected"   // never connected, or user-initiated disconnect
  | "connecting"    // initial connect in flight
  | "connected"     // healthy
  | "reconnecting"  // unexpected leave; bounded retry loop in progress
  | "failed"        // retries exhausted; user must trigger a manual reconnect

export type ConnectionStatusListener = (
  status: ConnectionStatus,
  detail: { attempt?: number; maxAttempts?: number; error?: string } | null,
) => void

/** Reconnect backoff (ms). 2/5/10/20/30s = ~67s before surfacing "failed". */
const RECONNECT_BACKOFF_MS = [2_000, 5_000, 10_000, 20_000, 30_000] as const

export class OrgRoomClient {
  private static instance: OrgRoomClient | null = null
  private client: Client
  private room: Room | null = null

  /**
   * Last successful connect args, kept across drops so the reconnect path
   * can re-issue ``joinOrCreate`` without the caller having to remember.
   * Cleared on an explicit ``disconnect()`` so a deliberate teardown does
   * NOT trigger auto-reconnect.
   */
  private lastConnectArgs: {
    orgId: string
    userData: { userId: string; name: string; characterModel?: string; token?: string }
  } | null = null
  private reconnectAttempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  /** Listeners for the UI banner. */
  private statusListeners = new Set<ConnectionStatusListener>()
  private currentStatus: ConnectionStatus = "disconnected"

  /**
   * Cached mirror of server member state. Updated on every add/update/remove
   * so subsystems (e.g., InteriorManager) can query current state without
   * needing their own listener-managed cache.
   */
  private memberSnapshots = new Map<string, MemberStateSnapshot>()

  /** Fan-out listeners for subsystems that need to react to member changes. */
  private memberChangeListeners = new Set<MemberChangeListener>()

  /** Most recent snapshot of OrgRoomState.activeRaces, keyed by roomId. */
  private activeRaceSnapshots = new Map<string, ActiveRaceSummary>()
  private activeRaceListeners = new Set<(summaries: ActiveRaceSummary[]) => void>()

  /** Callbacks set by the engine. */
  onMemberAdd:    ((userId: string, data: MemberStateSnapshot) => void) | null = null
  onMemberUpdate: ((userId: string, data: MemberStateSnapshot) => void) | null = null
  onMemberRemove: ((userId: string) => void) | null = null

  onAgentAdd:    ((agentId: string, data: AgentStateSnapshot) => void) | null = null
  onAgentUpdate: ((agentId: string, data: AgentStateSnapshot) => void) | null = null
  onAgentRemove: ((agentId: string) => void) | null = null

  private constructor(serverUrl: string) {
    this.client = new Client(serverUrl)
  }

  static getInstance(serverUrl?: string): OrgRoomClient {
    if (!OrgRoomClient.instance) {
      OrgRoomClient.instance = new OrgRoomClient(serverUrl ?? resolveColyseusUrl())
    }
    return OrgRoomClient.instance
  }

  /** Whether we're currently connected to an org room. */
  get isConnected(): boolean {
    return this.room !== null
  }

  get sessionId(): string | undefined {
    return this.room?.sessionId
  }

  /**
   * Connect to the org room for the given org. Joins or creates
   * "org-{orgId}" on the Colyseus server. Sets up state listeners
   * for members and agents.
   */
  async connect(
    orgId: string,
    userData: { userId: string; name: string; characterModel?: string; token?: string },
  ): Promise<void> {
    if (this.room) {
      await this.disconnect()
    }

    // Cancel any pending reconnect — a fresh ``connect()`` supersedes the
    // background retry loop, otherwise an in-flight backoff might fire
    // mid-connect and clobber the new room.
    this.cancelPendingReconnect()
    this.lastConnectArgs = { orgId, userData }
    this.reconnectAttempt = 0
    this.setStatus("connecting", null)

    try {
      this.room = await this.client.joinOrCreate("org", {
        roomId: `org-${orgId}`,
        orgId,
        userId: userData.userId,
        name: userData.name,
        characterModel: userData.characterModel ?? '',
        token: userData.token ?? '',
      })
      this.setupStateListeners()
      this.registerOnLeave()
      this.setStatus("connected", null)
      console.debug(`[OrgRoomClient] Connected to org=${orgId} session=${this.room.sessionId}`)
    } catch (err) {
      console.warn("[OrgRoomClient] Failed to join org room:", err)
      this.setStatus("failed", { error: err instanceof Error ? err.message : String(err) })
      throw err
    }
  }

  /**
   * Register an ``onLeave`` handler so unexpected WebSocket drops are
   * detected instead of silently leaving ``this.room`` set to a dead
   * Room instance (which would let ``isConnected`` keep returning true
   * even though Colyseus has cleared its server-side state).
   *
   * Colyseus emits ``code = 1000`` for clean closes (server-initiated
   * leave, normal flow) and other codes for abnormal closes (network
   * drop, server restart, idle eviction). We only trigger auto-reconnect
   * on abnormal closes — a clean close means the caller deliberately
   * unsubscribed via ``disconnect()`` and we'd just race them.
   */
  private registerOnLeave(): void {
    if (!this.room) return
    this.room.onLeave((code) => {
      console.warn(`[OrgRoomClient] room.onLeave code=${code}`)
      this.clearRoomState()
      // Code 1000 = normal close. Anything else = treat as transient.
      if (code !== 1000 && this.lastConnectArgs) {
        this.scheduleReconnect()
      } else {
        this.setStatus("disconnected", null)
      }
    })
  }

  private scheduleReconnect(): void {
    if (!this.lastConnectArgs) return
    if (this.reconnectAttempt >= RECONNECT_BACKOFF_MS.length) {
      this.setStatus("failed", {
        attempt: this.reconnectAttempt,
        maxAttempts: RECONNECT_BACKOFF_MS.length,
      })
      return
    }

    const delayMs = RECONNECT_BACKOFF_MS[this.reconnectAttempt]
    this.reconnectAttempt += 1
    this.setStatus("reconnecting", {
      attempt: this.reconnectAttempt,
      maxAttempts: RECONNECT_BACKOFF_MS.length,
    })

    this.reconnectTimer = setTimeout(async () => {
      this.reconnectTimer = null
      const args = this.lastConnectArgs
      if (!args) return
      try {
        // Skip the public ``connect()`` shortcut path that resets
        // ``reconnectAttempt`` — we want to *continue* the backoff
        // ladder until success or exhaustion.
        this.room = await this.client.joinOrCreate("org", {
          roomId: `org-${args.orgId}`,
          orgId: args.orgId,
          userId: args.userData.userId,
          name: args.userData.name,
          characterModel: args.userData.characterModel ?? '',
          token: args.userData.token ?? '',
        })
        this.setupStateListeners()
        this.registerOnLeave()
        this.reconnectAttempt = 0
        this.setStatus("connected", null)
        console.debug(
          `[OrgRoomClient] Reconnected to org=${args.orgId} session=${this.room.sessionId}`,
        )
      } catch (err) {
        console.warn(
          `[OrgRoomClient] Reconnect attempt ${this.reconnectAttempt} failed:`,
          err,
        )
        this.scheduleReconnect()
      }
    }, delayMs)
  }

  private cancelPendingReconnect(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  /** Subscribe to connection status changes. Returns an unsubscribe function. */
  addConnectionStatusListener(listener: ConnectionStatusListener): () => void {
    this.statusListeners.add(listener)
    // Replay the current status immediately so subscribers don't miss the
    // state they joined on.
    listener(this.currentStatus, null)
    return () => {
      this.statusListeners.delete(listener)
    }
  }

  /** Caller-triggered retry — clears the "failed" state and starts fresh. */
  async retryConnect(): Promise<void> {
    if (!this.lastConnectArgs) {
      console.warn("[OrgRoomClient] retryConnect called with no prior connect args")
      return
    }
    this.cancelPendingReconnect()
    this.reconnectAttempt = 0
    await this.connect(this.lastConnectArgs.orgId, this.lastConnectArgs.userData)
  }

  private setStatus(
    status: ConnectionStatus,
    detail: { attempt?: number; maxAttempts?: number; error?: string } | null,
  ): void {
    this.currentStatus = status
    for (const listener of this.statusListeners) {
      try {
        listener(status, detail)
      } catch (err) {
        console.warn("[OrgRoomClient] status listener threw:", err)
      }
    }
  }

  private clearRoomState(): void {
    this.room = null
    this.memberSnapshots.clear()
    this.activeRaceSnapshots.clear()
  }

  /** Disconnect from the org room. */
  async disconnect(): Promise<void> {
    // User-initiated teardown — suppress the reconnect loop.
    this.cancelPendingReconnect()
    this.lastConnectArgs = null
    this.reconnectAttempt = 0
    if (!this.room) {
      this.setStatus("disconnected", null)
      return
    }
    try {
      await this.room.leave()
    } catch {
      // Already disconnected
    }
    this.clearRoomState()
    this.setStatus("disconnected", null)
    // Drop the 6 engine-owned callbacks. Each is an arrow function that
    // captured `this` (the GardenEngine) when wireOrgRoomCallbacks ran —
    // since OrgRoomClient is a process-lifetime singleton, leaving these
    // set after disconnect pins the entire destroyed pc.Application via
    // closure scope. Heap snapshot showed 1 retained Application per
    // dashboard mount, all rooted through these fields.
    //
    // We do NOT clear memberChangeListeners / activeRaceListeners — those
    // are subscriber-owned (their owners hold the unsubscribe fn from
    // addMemberChangeListener / addActiveRaceListener and call it on their
    // own teardown, e.g. InteriorManager.destroy → orgRoomUnsubscribe()).
    // Clearing them here would break the subscriber contract.
    this.onMemberAdd    = null
    this.onMemberUpdate = null
    this.onMemberRemove = null
    this.onAgentAdd     = null
    this.onAgentUpdate  = null
    this.onAgentRemove  = null
  }

  /** Send a position update (for takeover mode). */
  sendMove(x: number, y: number, z: number, yaw: number, animState: string): void {
    this.room?.send("move", { x, y, z, yaw, animState })
  }

  /** Send takeover start (server suspends NPC sim for this user). */
  sendTakeoverStart(userId: string): void {
    this.room?.send("takeover_start", { userId })
  }

  /**
   * Send takeover end (server resumes NPC sim).
   *
   * @param location  Optional destination. When set (e.g. "cafeteria",
   *   "coffeebar"), the server parks the character at that locationContext
   *   instead of running walkHome, and every viewer's CharacterSystem hides
   *   the avatar for the duration of the interior visit.
   */
  sendTakeoverEnd(userId: string, location?: string): void {
    this.room?.send("takeover_end", { userId, location })
  }

  /** Send vehicle mount command. */
  sendMountVehicle(vehicleId: string): void {
    this.room?.send("mount_vehicle", { vehicleId })
  }

  /** Send vehicle dismount command. */
  sendDismountVehicle(): void {
    this.room?.send("dismount_vehicle", {})
  }

  /** Notify server of house tier upgrade (live update for all viewers). */
  sendUpgradeHouse(tier: number): void {
    this.room?.send("upgrade_house", { tier })
  }

  /**
   * Send a `race_create` request and resolve with the new room id.
   *
   * Correlated request/response pattern: the server answers with either
   * `race_created` (success) or `race_create_failed` (server-side
   * rejection). Timeout after 5 s so a dropped response doesn't hang
   * the caller's dialog forever.
   */
  async sendRaceCreate(body: {
    invitedUserIds: string[]
    distanceM: number
  }): Promise<{ roomId: string }> {
    if (!this.room) throw new Error("OrgRoomClient: not connected")
    const room = this.room
    return new Promise<{ roomId: string }>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        cleanup()
        reject(new Error("race_create timed out"))
      }, RACE_CREATE_TIMEOUT_MS)

      const cleanup = (): void => {
        window.clearTimeout(timeout)
        okHandle?.()
        failHandle?.()
      }
      const okHandle = room.onMessage("race_created", (msg: { roomId: string }) => {
        cleanup()
        resolve({ roomId: msg.roomId })
      })
      const failHandle = room.onMessage(
        "race_create_failed",
        (msg: { reason: string }) => {
          cleanup()
          reject(new Error(`race_create failed: ${msg.reason}`))
        },
      )
      room.send("race_create", body)
    })
  }

  /**
   * Subscribe to changes in `OrgRoomState.activeRaces`. Called for every
   * add/change/remove on the MapSchema, giving the watch banner enough
   * signal to render itself. Returns an unsubscribe function.
   */
  addActiveRaceListener(listener: (summaries: ActiveRaceSummary[]) => void): () => void {
    this.activeRaceListeners.add(listener)
    listener(Array.from(this.activeRaceSnapshots.values()))
    return () => { this.activeRaceListeners.delete(listener) }
  }

  /** Temporary dev tool: fire a simulated dev_activity for the current user. */
  sendSimulateDevActivity(): void {
    this.room?.send("simulate_dev_activity")
  }

  // ─── Member state query API (Phase 8) ────────────

  /** Read a member snapshot by userId. Returns null if not present. */
  getMember(userId: string): MemberStateSnapshot | null {
    return this.memberSnapshots.get(userId) ?? null
  }

  /** Readonly view of all currently known members. */
  get members(): ReadonlyMap<string, MemberStateSnapshot> {
    return this.memberSnapshots
  }

  /**
   * Subscribe to member state changes. The listener is called with
   * (userId, snapshot) on add/update and (userId, null) on remove.
   * Returns an unsubscribe function.
   */
  addMemberChangeListener(listener: MemberChangeListener): () => void {
    this.memberChangeListeners.add(listener)
    return () => { this.memberChangeListeners.delete(listener) }
  }

  private emitMemberChange(userId: string, snapshot: MemberStateSnapshot | null): void {
    for (const listener of this.memberChangeListeners) {
      try {
        listener(userId, snapshot)
      } catch (err) {
        console.warn("[OrgRoomClient] member change listener threw:", err)
      }
    }
  }

  // ─── State listener setup ────────────────────

  /**
   * Wire up Colyseus schema-sync callbacks via the 0.17 callback proxy.
   *
   * In Colyseus 0.17, `MapSchema.onAdd/onRemove` are NOT available on the
   * raw schema instance — you have to access them via a callback proxy
   * returned by `getStateCallbacks(room)`. Reading them directly off
   * `room.state.members` returns undefined and silently misses every
   * state delta, which is why this was broken before.
   *
   * The `immediate: true` flag on `onAdd` ensures the listener fires for
   * entries that already existed in the state when we attach — critical
   * because the server loads the snapshot in `onCreate` before the client
   * joins, so all members are pre-existing from the client's perspective.
   */
  private setupStateListeners(): void {
    if (!this.room) return
    const room = this.room as Room<OrgRoomStateShape>
    const $ = getStateCallbacks(room)
    const stateProxy = $(room.state)

    stateProxy.members.onAdd((member, userId) => {
      const snapshot = memberToSnapshot(member)
      this.memberSnapshots.set(userId, snapshot)
      this.onMemberAdd?.(userId, snapshot)
      this.emitMemberChange(userId, snapshot)
      $(member).onChange(() => {
        const updated = memberToSnapshot(member)
        this.memberSnapshots.set(userId, updated)
        this.onMemberUpdate?.(userId, updated)
        this.emitMemberChange(userId, updated)
      })
    }, true /* immediate: fire for pre-existing entries */)

    stateProxy.members.onRemove((_member, userId) => {
      this.memberSnapshots.delete(userId)
      this.onMemberRemove?.(userId)
      this.emitMemberChange(userId, null)
    })

    stateProxy.agents.onAdd((agent, agentId) => {
      this.onAgentAdd?.(agentId, agentToSnapshot(agent))
      $(agent).onChange(() => {
        this.onAgentUpdate?.(agentId, agentToSnapshot(agent))
      })
    }, true)

    stateProxy.agents.onRemove((_agent, agentId) => {
      this.onAgentRemove?.(agentId)
    })

    // Active-race map — drives the garden watch banner. One callback fires
    // on every MapSchema mutation; we rebuild and publish the full list.
    const emitActiveRaces = (): void => {
      const list = Array.from(this.activeRaceSnapshots.values())
      for (const listener of this.activeRaceListeners) {
        try { listener(list) } catch (err) {
          console.warn("[OrgRoomClient] active-race listener threw:", err)
        }
      }
    }

    stateProxy.activeRaces.onAdd((race, roomId) => {
      this.activeRaceSnapshots.set(roomId, activeRaceToSnapshot(race))
      emitActiveRaces()
      $(race).onChange(() => {
        this.activeRaceSnapshots.set(roomId, activeRaceToSnapshot(race))
        emitActiveRaces()
      })
    }, true)

    stateProxy.activeRaces.onRemove((_race, roomId) => {
      this.activeRaceSnapshots.delete(roomId)
      emitActiveRaces()
    })
  }
}

function activeRaceToSnapshot(r: RawActiveRace): ActiveRaceSummary {
  return {
    roomId:     r.roomId      ?? '',
    hostUserId: r.hostUserId  ?? '',
    hostName:   r.hostName    ?? '',
    distanceM:  r.distanceM   ?? 0,
    phase:      r.phase       ?? 'lobby',
    racerCount: r.racerCount  ?? 0,
    // ArraySchema on the wire behaves like ArrayLike — convert to a plain
    // readonly string[] so downstream Vue code can `.includes()` without
    // pulling the Colyseus proxy semantics into the frontend.
    participantUserIds: r.participantUserIds
      ? Array.from(r.participantUserIds as ArrayLike<string>)
      : [],
  }
}

// ─── Helpers ────────────────────────────────

/** Structural shape the callback proxy needs — matches server OrgRoomState. */
interface OrgRoomStateShape {
  members: Map<string, RawMember>
  agents: Map<string, RawAgent>
  activeRaces: Map<string, RawActiveRace>
}

function memberToSnapshot(m: RawMember): MemberStateSnapshot {
  return {
    userId:         m.userId          ?? '',
    name:           m.name            ?? '',
    characterModel: m.characterModel  ?? '',
    level:          m.level           ?? 0,
    levelName:      m.levelName       ?? '',
    presence:       m.presence        ?? 'active',
    x:              m.x               ?? 0,
    y:              m.y               ?? 0,
    z:              m.z               ?? 0,
    yaw:            m.yaw             ?? 0,
    animState:      m.animState       ?? 'idle',
    labelName:      m.labelName       ?? '',
    labelMessage:   m.labelMessage    ?? '',
    takeoverSessionId: m.takeoverSessionId ?? '',
    locationContext: m.locationContext ?? 'garden',
    vehicleId:      m.vehicleId       ?? '',
    houseLevel:     m.houseLevel      ?? 1,
  }
}

function agentToSnapshot(a: RawAgent): AgentStateSnapshot {
  return {
    agentId:    a.agentId    ?? '',
    skillSlug:  a.skillSlug  ?? '',
    skillName:  a.skillName  ?? '',
    actorName:  a.actorName  ?? '',
    repoName:   a.repoName   ?? '',
    budNumber:  a.budNumber  ?? 0,
    x:          a.x          ?? 0,
    y:          a.y          ?? 0,
    z:          a.z          ?? 0,
    yaw:        a.yaw        ?? 0,
    state:      a.state      ?? 'spawning',
    action:     a.action     ?? '',
    message:    a.message    ?? '',
  }
}
