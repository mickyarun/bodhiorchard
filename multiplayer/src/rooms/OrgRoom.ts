/**
 * OrgRoom — Colyseus room for one org's 3D world.
 *
 * Room ID pattern: "org-{orgId}"
 * One room per org. All clients viewing the same org dashboard join
 * the same room and see the same server-authoritative world state.
 *
 * Responsibilities (added in later phases):
 *   - Initial member placement from presence state (Phase 2)
 *   - Dev activity simulation: walk-to-tree, return-to-seat (Phase 5)
 *   - Agent/robot simulation (Phase 6)
 *   - Takeover: player-authoritative position for specific members (Phase 7)
 *
 * Messages:
 *   "move" → { x, y, z, yaw, animState } — player takeover position update (~20Hz)
 *   "takeover_start" → { userId } — begin player control of a member
 *   "takeover_end" → { userId } — end player control
 *
 * Backend bridge messages (authenticated via shared secret HTTP endpoint):
 *   "bridge:dev_activity" → dev activity event forwarded from backend
 *   "bridge:agent_activity" → agent activity event forwarded from backend
 */
import { Room, Client } from "colyseus"
import { OrgRoomState } from "../schema/OrgRoomState"
import { MemberState } from "../schema/MemberState"
import { computePlacement } from "../sim/MemberPlacement"
import { getTreePositions } from "../sim/WorldLayout"
import { DevActivitySim, parseDevActivityEvent } from "../sim/DevActivitySim"
import { AgentActivitySim, parseAgentActivityEvent } from "../sim/AgentActivitySim"
import {
  fetchOrgSnapshot,
  verifyUserToken,
  type OrgSnapshotResponse,
} from "../bridge/BackendClient"
import { registerOrgRoom, unregisterOrgRoom } from "../bridge/BridgeEndpoint"

// Server simulation tick rate — 20Hz matches Colyseus default state sync cadence
const SIM_TICK_MS = 50

// Minimum interval between accepted move messages per client. Clients throttle
// themselves to ~20Hz (50ms) — we enforce a slightly lower bound to allow
// jitter. Messages arriving faster are dropped to prevent single-client DoS.
const MIN_MOVE_INTERVAL_MS = 25

interface OrgRoomCreateOptions {
  orgId?: string
}

interface OrgRoomJoinOptions {
  userId: string
  name: string
  characterModel?: string
  token?: string
}

interface MoveMessage {
  x: number
  y: number
  z: number
  yaw: number
  animState: string
}

interface TakeoverMessage {
  userId: string
}

export class OrgRoom extends Room<{ state: OrgRoomState }> {
  maxClients = 100

  // Repo tree positions from snapshot — used by DevActivitySim
  repoPositions = new Map<string, { x: number; z: number }>()

  // Server-side dev activity simulation (walk-to-tree, phrase cycling, return-to-seat)
  private devSim = new DevActivitySim(this.repoPositions)

  // Server-side agent/robot simulation (spawn, walk between repo trees, despawn)
  private agentSim = new AgentActivitySim(this.repoPositions)

  // Resolves once the initial snapshot has been loaded (or failed).
  // onJoin awaits this so late joiners never race against an empty state map.
  private snapshotReady!: Promise<void>

  // Valid animation states accepted from client move messages
  private static readonly VALID_ANIMS = [
    "idle", "walk", "sit", "sleep", "sprint", "jump",
  ]

  async onCreate(options: OrgRoomCreateOptions) {
    this.setState(new OrgRoomState())
    this.state.orgId = options.orgId ?? ""
    console.log(`[OrgRoom] Created org=${this.state.orgId}`)

    this.onMessage("move", (client, data: MoveMessage) => this.handleMove(client, data))
    this.onMessage("takeover_start", (client, data: TakeoverMessage) => this.handleTakeoverStart(client, data))
    this.onMessage("takeover_end", (client, data: TakeoverMessage) => this.handleTakeoverEnd(client, data))

    // Drive the server-side simulation at 20Hz — walking, phrase cycles, idle timeouts.
    // setSimulationInterval passes dt in milliseconds; sim tick expects seconds.
    this.setSimulationInterval((dtMs) => {
      const dt = dtMs / 1000
      this.devSim.tick(this.state.members, dt)
      this.agentSim.tick(this.state.agents, dt)
    }, SIM_TICK_MS)

    // Kick off snapshot load and expose a promise so onJoin can wait for it.
    // onCreate MUST NOT throw — the room stays usable (empty state) on failure.
    this.snapshotReady = this.loadInitialSnapshot()
  }

  /**
   * Fetch the initial org snapshot from the backend. Wrapped so that the
   * promise captures all error paths (fetch failure, parse failure, disposal)
   * and resolves cleanly so onJoin can `await` it without risk of rejection.
   */
  private async loadInitialSnapshot(): Promise<void> {
    if (!this.state.orgId) return
    registerOrgRoom(this.state.orgId, this)
    try {
      const snapshot = await fetchOrgSnapshot(this.state.orgId)
      if (snapshot) {
        this.loadSnapshot(snapshot)
      } else {
        console.warn(`[OrgRoom] No snapshot available for org=${this.state.orgId}`)
      }
    } catch (err) {
      console.error(`[OrgRoom] Snapshot load failed for org=${this.state.orgId}:`, err)
    }
  }

  /**
   * Verify the client's JWT against the backend before allowing them to join.
   * This is the ONLY point where client-supplied `userId` / `name` are trusted;
   * everything downstream uses the values returned from this verification.
   *
   * In development (`NODE_ENV !== "production"`), if no token is supplied the
   * room accepts the client-supplied identity as-is — local dev tooling and
   * unit tests don't go through login. In production, a missing/invalid token
   * rejects the join.
   */
  async onAuth(_client: Client, options: OrgRoomJoinOptions): Promise<OrgRoomJoinOptions> {
    const orgId = this.state.orgId || ""
    if (!options.token) {
      if (process.env.NODE_ENV === "production") {
        throw new Error("auth token required")
      }
      console.warn(`[OrgRoom] dev-mode join without token org=${orgId} userId=${options.userId}`)
      return options
    }
    const result = await verifyUserToken(options.token, orgId)
    if (!result.valid) {
      throw new Error("invalid auth token")
    }
    // The token's org claim must match the room's org — prevents cross-org spying.
    if (orgId && result.org_id && result.org_id !== orgId) {
      throw new Error("token org mismatch")
    }
    // Authoritative values from the verified token REPLACE client-supplied claims.
    return {
      ...options,
      userId: result.user_id ?? options.userId,
      name: result.name ?? options.name,
    }
  }

  async onJoin(client: Client, options: OrgRoomJoinOptions) {
    // Wait for the initial snapshot before deciding if the joining user is
    // a known member — prevents a race where the first client races against
    // onCreate's async fetch and sees an empty members map.
    await this.snapshotReady
    console.log(`[OrgRoom] ${options.name ?? "Unknown"} (${client.sessionId}) joined org=${this.state.orgId}`)
    // Per-client identity is tracked via client.userData so we can attribute
    // moves/takeovers to the correct memberId later. These values come from
    // onAuth, which verified them against a JWT.
    client.userData = {
      userId: options.userId,
      name: options.name,
      characterModel: options.characterModel ?? "",
    }
    // Users not present in this.state.members at join time indicate a snapshot
    // mismatch — the backend's `/internal/colyseus/org-snapshot` endpoint is
    // responsible for returning every active org member. If you see this
    // warning, check `_collect_org_members` in backend/app/api/v1/internal_colyseus.py.
    if (options.userId && !this.state.members.has(options.userId)) {
      console.warn(
        `[OrgRoom] joining user ${options.userId} not in snapshot — ` +
        `snapshot endpoint may be filtering members`,
      )
    }
  }

  onLeave(client: Client) {
    const name = (client.userData as { name?: string } | undefined)?.name ?? client.sessionId
    console.log(`[OrgRoom] ${name} left org=${this.state.orgId}`)

    // Clear takeover flag if this client was controlling a member
    const userId = (client.userData as { userId?: string } | undefined)?.userId
    if (userId) {
      const member = this.state.members.get(userId)
      if (member && member.takeoverSessionId === client.sessionId) {
        member.takeoverSessionId = ""
      }
    }
  }

  onDispose() {
    console.log(`[OrgRoom] Disposed org=${this.state.orgId}`)
    if (this.state.orgId) {
      unregisterOrgRoom(this.state.orgId)
    }
  }

  /**
   * Handle an event forwarded from the backend via the bridge endpoint.
   * dev_activity → routed to DevActivitySim; agent_activity → Phase 6.
   */
  handleBridgeEvent(type: string, data: Record<string, unknown>): void {
    if (type === "dev_activity") {
      const event = parseDevActivityEvent(data)
      if (!event) {
        console.warn(`[OrgRoom] Malformed dev_activity payload org=${this.state.orgId}`)
        return
      }
      this.devSim.handleEvent(this.state.members, event)
      return
    }
    if (type === "agent_activity") {
      const event = parseAgentActivityEvent(data)
      if (!event) {
        console.warn(`[OrgRoom] Malformed agent_activity payload org=${this.state.orgId}`)
        return
      }
      this.agentSim.handleEvent(this.state.agents, event)
      return
    }
    console.log(`[OrgRoom] Bridge event type=${type} (unhandled) org=${this.state.orgId}`)
  }

  // ─── Snapshot loading ────────────────────────

  /**
   * Load a snapshot of org data from the backend.
   * Replaces existing members, computes initial placement from presence.
   * Idempotent — safe to call multiple times.
   *
   * Member ordering invariant: house assignment depends on stable ordering
   * (index → house grid slot). We sort by user_id to guarantee the same
   * house slot across snapshot reloads regardless of backend ordering.
   */
  loadSnapshot(snapshot: OrgSnapshotResponse): void {
    // Preserve takeover sessions across snapshot reloads
    const takeoverPreserve = new Map<string, string>()
    this.state.members.forEach((m, key) => {
      if (m.takeoverSessionId) takeoverPreserve.set(key, m.takeoverSessionId)
    })
    this.state.members.clear()

    // Drop any in-flight dev activity state — its cached originalX/Z/wasSitting
    // point to desks from the previous house grid and would send members to
    // stale positions on return-to-seat.
    this.devSim.reset()

    // Drop any in-flight agents — tree coords are about to be rebuilt and
    // existing AgentEntries cache targetX/Z against the old positions.
    this.agentSim.reset(this.state.agents)

    // Compute repo tree positions (used by Phase 5 dev_activity sim)
    this.repoPositions.clear()
    const repoNames = snapshot.repos?.map(r => r.repo_name).sort() ?? []
    const treeCoords = getTreePositions(repoNames.length)
    repoNames.forEach((name, i) => {
      if (treeCoords[i]) this.repoPositions.set(name, treeCoords[i])
    })

    // Stable sort by user_id — guarantees deterministic house assignment
    const sorted = [...snapshot.members].sort((a, b) => a.user_id.localeCompare(b.user_id))

    const takenBreakSeats = new Set<number>()
    sorted.forEach((m, index) => {
      const placement = computePlacement(
        {
          userId: m.user_id,
          presence: m.presence,
          memberIndex: index,
          totalMembers: sorted.length,
        },
        takenBreakSeats,
      )

      const member = new MemberState()
      member.userId = m.user_id
      member.name = m.name
      member.characterModel = m.character_model ?? ""
      member.level = m.level ?? 0
      member.levelName = m.level_name ?? ""
      member.presence = m.presence
      member.x = placement.x
      member.y = placement.y
      member.z = placement.z
      member.yaw = placement.yaw
      member.animState = placement.sitting ? "sit" : "idle"
      member.locationContext = placement.locationContext
      member.takeoverSessionId = takeoverPreserve.get(m.user_id) ?? ""

      this.state.members.set(m.user_id, member)
    })

    console.log(`[OrgRoom] Snapshot loaded org=${this.state.orgId} members=${sorted.length}`)
  }

  // ─── Message handlers ────────────────────────

  private handleMove(client: Client, data: MoveMessage): void {
    if (!this.validateMove(data)) return

    // Rate limit per-client to prevent a single malicious connection from
    // flooding the room's state sync broadcast. `lastMoveAt` lives on
    // userData so it's garbage-collected with the client.
    const userData = client.userData as
      { userId?: string; lastMoveAt?: number } | undefined
    if (!userData?.userId) return
    const now = Date.now()
    if (userData.lastMoveAt && now - userData.lastMoveAt < MIN_MOVE_INTERVAL_MS) {
      return
    }
    userData.lastMoveAt = now

    const member = this.state.members.get(userData.userId)
    if (!member) return

    // Only apply move if this client is the active takeover controller
    if (member.takeoverSessionId !== client.sessionId) return

    member.x = data.x
    member.y = data.y
    member.z = data.z
    member.yaw = data.yaw
    member.animState = data.animState
  }

  private handleTakeoverStart(client: Client, data: TakeoverMessage): void {
    const clientUserId = (client.userData as { userId?: string } | undefined)?.userId
    if (!clientUserId) return
    // Users can only take control of their own character
    if (clientUserId !== data.userId) return

    const member = this.state.members.get(data.userId)
    if (!member) return

    // Once a player starts driving their character, they're no longer sitting
    // at a desk/bed or at a repo tree — they're out in the garden. Clearing
    // locationContext prevents stale interior NPC spawns (e.g., a visitor
    // seeing a ghost of the owner at their desk while the owner is WASD-ing).
    member.locationContext = "garden"
    member.takeoverSessionId = client.sessionId
    console.log(`[OrgRoom] ${member.name} takeover START by ${client.sessionId}`)
  }

  private handleTakeoverEnd(client: Client, data: TakeoverMessage): void {
    const member = this.state.members.get(data.userId)
    if (!member) return
    if (member.takeoverSessionId !== client.sessionId) return

    // Clean up any transient takeover pose (mid-jump, sprint) before handing
    // control back to the sim. Prevents other viewers from seeing the member
    // frozen in the air or at a stale Y until the next dev_activity event.
    member.y = 0
    if (member.animState === "jump" || member.animState === "sprint") {
      member.animState = "idle"
    }
    member.takeoverSessionId = ""
    console.log(`[OrgRoom] ${member.name} takeover END`)
  }

  // ─── Validation ──────────────────────────────

  private validateMove(data: MoveMessage): boolean {
    if (typeof data.x !== "number" || !isFinite(data.x)) return false
    if (typeof data.y !== "number" || !isFinite(data.y)) return false
    if (typeof data.z !== "number" || !isFinite(data.z)) return false
    if (typeof data.yaw !== "number" || !isFinite(data.yaw)) return false
    if (!OrgRoom.VALID_ANIMS.includes(data.animState)) return false
    return true
  }
}
