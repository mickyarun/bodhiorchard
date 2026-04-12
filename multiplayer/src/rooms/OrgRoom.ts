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
import {
  computePlacement,
  type Placement,
  type PresenceState,
} from "../sim/MemberPlacement"
import { BREAK_SEATS, getTreePositions } from "../sim/WorldLayout"
import {
  DevActivitySim,
  parseDevActivityEvent,
  type HomeCoords,
} from "../sim/DevActivitySim"
import { AgentActivitySim, parseAgentActivityEvent } from "../sim/AgentActivitySim"
import { InferredPresenceSim, buildPresenceConfig } from "../sim/InferredPresenceSim"
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

// InferredPresenceSim tick rate — 60 seconds. Inferred presence is derived
// from time-of-day and idle thresholds (10 / 20 minutes), so evaluating more
// often than once per minute would waste cycles without adding responsiveness.
const INFERRED_PRESENCE_TICK_MS = 60_000

// How many InferredPresenceSim ticks pass between snapshot re-fetches. At
// 60s/tick × 15 = 15 minutes, this is the maximum latency for a PATCH on
// /v1/settings/connections (presence section) to reach a live OrgRoom. See
// the plan follow-up note for an eventual push-on-PATCH bridge.
const SNAPSHOT_REFRESH_EVERY_N_TICKS = 15

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

  // Server-side dev activity simulation (walk-to-tree, phrase cycling, return-to-seat).
  // The second argument is a live home resolver: when the sim returns a member
  // to their seat after a dev session, it consults this callback for the CURRENT
  // home coordinates rather than using the cached originals. This is how a
  // presence change mid-dev-activity lands the member at the new seat. Field
  // initializers run in declaration order, so `this.repoPositions` is already
  // set; the arrow function defers method access to call time (after the
  // constructor finishes), which is when returnToSeat would actually invoke it.
  private devSim = new DevActivitySim(
    this.repoPositions,
    (userId) => this.resolveHomeCoords(userId),
  )

  // Server-side agent/robot simulation (spawn, walk between repo trees, despawn)
  private agentSim = new AgentActivitySim(this.repoPositions)

  // Inferred presence simulation — drives pseudo-presence for non-Slack users
  // from their dev-activity history + time of day. Skips Slack-driven members
  // (they get real presence via Phase B bridge events) and takeover-controlled
  // members (player input wins). Callback wired to applyPresenceChange so the
  // walk-home machinery is shared with Slack-driven updates.
  private inferredSim = new InferredPresenceSim(
    (userId, presence, preferredZone) =>
      this.applyPresenceChange(userId, presence, preferredZone),
  )

  // Set of userIds whose presence is authoritatively driven by Slack.
  // Populated by loadSnapshot from the backend-supplied `has_slack` field.
  // Members in this set are skipped by InferredPresenceSim.tick so the two
  // presence sources don't fight each other.
  private hasSlack = new Set<string>()

  // Counter for the snapshot re-fetch cadence. See SNAPSHOT_REFRESH_EVERY_N_TICKS.
  private presenceTickCounter = 0

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
    //
    // NOTE: `setSimulationInterval` is SINGULAR in Colyseus — a second call
    // silently overwrites the first. For the slower InferredPresenceSim
    // timer below we use `this.clock.setInterval` instead, which supports
    // multiple independent schedules.
    this.setSimulationInterval((dtMs) => {
      const dt = dtMs / 1000
      this.devSim.tick(this.state.members, dt)
      this.agentSim.tick(this.state.agents, dt)
    }, SIM_TICK_MS)

    // Separate slow-tick loop for InferredPresenceSim (once per minute).
    // The inferred presence rules key off time-of-day and minute-scale idle
    // thresholds, so evaluating at 20Hz would waste 1,199 cycles out of 1,200.
    // `new Date()` is read here (not inside the sim) so test code can drive
    // the sim with arbitrary timestamps without monkey-patching the clock.
    //
    // Uses `this.clock.setInterval` (Colyseus Clock API) rather than a
    // second `setSimulationInterval` call, which would overwrite the 20Hz
    // devSim/agentSim timer and silently halt walking-home position ticks.
    this.clock.setInterval(() => {
      this.inferredSim.tick(this.state.members, this.hasSlack, new Date())
      this.presenceTickCounter += 1
      // Every N ticks (default 15 min), re-fetch the snapshot so live rooms
      // pick up per-org presence settings changes (working days, hours,
      // timezone, auto-mode). Full snapshot is refetched for simplicity —
      // we only apply the presence config via setConfig, NOT reload members
      // (which would disrupt seat assignments and takeovers).
      if (this.presenceTickCounter % SNAPSHOT_REFRESH_EVERY_N_TICKS === 0) {
        void this.refreshPresenceConfig()
      }
    }, INFERRED_PRESENCE_TICK_MS)

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
   * Lightweight periodic refresh of per-org presence configuration.
   *
   * Called by the InferredPresenceSim tick loop every
   * `SNAPSHOT_REFRESH_EVERY_N_TICKS` ticks (≈15 min) so live rooms pick
   * up settings changes (working days, hours, timezone, auto-mode)
   * without needing a client-driven room recreation or a server-push
   * channel. Only the presence config is re-applied — members, repos,
   * seats, and takeover sessions are intentionally left untouched
   * because those should be stable across a settings tweak.
   */
  private async refreshPresenceConfig(): Promise<void> {
    if (!this.state.orgId) return
    try {
      const snapshot = await fetchOrgSnapshot(this.state.orgId)
      if (!snapshot) return
      this.inferredSim.setConfig(buildPresenceConfig(snapshot.presenceSettings))
    } catch (err) {
      console.warn(
        `[OrgRoom] presence-config refresh failed for org=${this.state.orgId}:`,
        err,
      )
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

    // If this client was controlling a member via takeover, release the
    // takeover lock AND start a walk-home so the character doesn't strand
    // wherever the player last WASD'd to. Without this, a disconnect leaves
    // the member at garden coordinates with `locationContext = "garden"` —
    // next time the player logs back in, their character is in the middle
    // of the map instead of at their desk.
    //
    // Mirrors `handleTakeoverEnd` but is triggered by the WS close path
    // rather than an explicit takeover_end message. We walk for the same
    // reason the explicit path does.
    const userId = (client.userData as { userId?: string } | undefined)?.userId
    if (!userId) return
    const member = this.state.members.get(userId)
    if (!member) return
    if (member.takeoverSessionId !== client.sessionId) return

    member.y = 0
    if (member.animState === "jump" || member.animState === "sprint") {
      member.animState = "idle"
    }
    member.takeoverSessionId = ""

    const home = this.computeHomePlacement(
      userId,
      member.presence as PresenceState,
    )
    this.devSim.walkHome(member, home.x, home.z, home.yaw, home.sitting)
    console.log(
      `[OrgRoom] ${name} disconnect-while-takeover → walking home to ${home.locationContext}`,
    )
  }

  onDispose() {
    console.log(`[OrgRoom] Disposed org=${this.state.orgId}`)
    if (this.state.orgId) {
      unregisterOrgRoom(this.state.orgId)
    }
  }

  /**
   * Handle an event forwarded from the backend via the bridge endpoint.
   * dev_activity → routed to DevActivitySim
   * agent_activity → routed to AgentActivitySim
   * member_presence → live presence update, routed to applyPresenceChange
   */
  handleBridgeEvent(type: string, data: Record<string, unknown>): void {
    if (type === "dev_activity") {
      const event = parseDevActivityEvent(data)
      if (!event) {
        console.warn(`[OrgRoom] Malformed dev_activity payload org=${this.state.orgId}`)
        return
      }
      this.devSim.handleEvent(this.state.members, event)
      // Also inform the inferred-presence sim so it can reset the member's
      // idle timer. Skip if the user_id didn't resolve — no observable user
      // to track. Non-Slack users rely on this to stay in the "active" state.
      if (event.user_id) {
        this.inferredSim.recordDevActivity(event.user_id, new Date())
      }
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
    if (type === "member_presence") {
      const event = parseMemberPresenceEvent(data)
      if (!event) {
        console.warn(`[OrgRoom] Malformed member_presence payload org=${this.state.orgId}`)
        return
      }
      this.applyPresenceChange(event.user_id, event.presence)
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

    // Drop inferred presence traces — day keys and member IDs may have
    // drifted since the last snapshot. The sim will rebuild its trace map
    // as new dev_activity events arrive.
    this.inferredSim.reset()

    // Apply per-org presence configuration (working days, hours, timezone,
    // auto-mode). Undefined snapshot.presenceSettings → legacy defaults.
    this.inferredSim.setConfig(buildPresenceConfig(snapshot.presenceSettings))

    // Rebuild the has_slack skip set from the snapshot. Members without
    // this field default to false (treated as non-Slack → inferred presence
    // applies). See BackendClient.OrgSnapshotMember for the contract.
    this.hasSlack.clear()
    for (const m of snapshot.members) {
      if (m.has_slack) this.hasSlack.add(m.user_id)
    }

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

  // ─── Placement helpers ───────────────────────

  /**
   * Compute a member's "home" placement for the current room state.
   *
   * Unlike the one-shot placement done at snapshot load time, this method
   * is meant to be called live — after takeover exit, after a presence
   * change, etc. It:
   *
   * 1. Derives a stable member index from a sorted snapshot of live
   *    `state.members` (sort key: `userId`) so the house grid assignment
   *    matches what snapshot load would have produced.
   * 2. Computes break-seat occupancy from live state — iterates all OTHER
   *    on-break members and reserves whichever BREAK_SEATS indices their
   *    `locationContext` tags match. Prevents double-booking.
   * 3. Delegates to `computePlacement` which owns the actual seat math.
   *
   * Single source of truth used by `handleTakeoverEnd` today, and will be
   * reused by presence-change handling and inferred-presence ticks as those
   * features land. Any future caller that needs "where should this member be
   * right now based on their presence?" should call here, not reinvent.
   *
   * Complexity: O(N) where N = member count. Only called on infrequent
   * events (takeover exit, presence change) — not per-frame.
   *
   * @param userId        The member to place.
   * @param presence      The presence to place them as (may differ from
   *                      `member.presence` when recomputing after a change).
   * @param preferredZone Optional hint for `on_break` placement — e.g.
   *                      `"cafeteria"` for idle users, `"pool_resort"` for
   *                      morning-no-activity users. Ignored for other presences.
   * @returns Placement with x/y/z/yaw/sitting/locationContext set.
   */
  private computeHomePlacement(
    userId: string,
    presence: PresenceState,
    preferredZone?: string,
  ): Placement {
    // Stable order → stable house grid slot assignment.
    const sorted = [...this.state.members.values()]
      .sort((a, b) => a.userId.localeCompare(b.userId))
    const memberIndex = sorted.findIndex(m => m.userId === userId)

    // Reserve break seats already occupied by OTHER on-break members, so we
    // don't seat this member on top of someone else. We read occupancy from
    // `locationContext` (format `break_{zone}_{seatIndex}`) rather than
    // coordinates so a member mid-walk who hasn't physically arrived yet
    // still reserves their target seat.
    //
    // The trailing numeric index disambiguates within a zone — BREAK_SEATS
    // has 4 seats per zone (coffee_bar, pool_resort, cafeteria), so walking
    // from `break_cafeteria_0` to `break_cafeteria_2` is a legal parallel
    // occupancy that must not double-book.
    const takenBreakSeats = new Set<number>()
    for (const other of sorted) {
      if (other.userId === userId) continue
      if (other.presence !== "on_break") continue
      const match = other.locationContext.match(/^break_.+_(\d+)$/)
      if (!match) continue
      const seatIdx = parseInt(match[1], 10)
      if (seatIdx >= 0 && seatIdx < BREAK_SEATS.length) {
        takenBreakSeats.add(seatIdx)
      }
    }

    return computePlacement(
      {
        userId,
        presence,
        memberIndex,
        totalMembers: sorted.length,
      },
      takenBreakSeats,
      preferredZone,
    )
  }

  /**
   * Home-resolver callback supplied to DevActivitySim's constructor.
   *
   * The sim calls this at `returnToSeat` time (i.e. when a dev session ends
   * naturally via idle timeout or session_end event). Reading `member.presence`
   * at call time — not at session start — is what makes mid-session presence
   * changes route the member to their NEW seat on arrival, instead of the
   * stale original. Returns `null` if the member is gone from state so the
   * sim can fall back to its cached originals.
   */
  private resolveHomeCoords(userId: string): HomeCoords | null {
    const member = this.state.members.get(userId)
    if (!member) return null
    const home = this.computeHomePlacement(
      userId,
      member.presence as PresenceState,
    )
    return {
      x: home.x,
      z: home.z,
      yaw: home.yaw,
      sitting: home.sitting,
    }
  }

  /**
   * Apply a presence change to a member and walk them to the new seat.
   *
   * This is the shared primitive used by both Slack-driven presence updates
   * (bridge event `member_presence` in Phase B) and inferred-presence ticks
   * (`InferredPresenceSim` in Phase C). Callers just pass the new presence;
   * this method owns the decision tree:
   *
   * 1. No-op if the member is unknown or presence didn't change (idempotent).
   * 2. Update the live `member.presence` field so subsequent lookups see the
   *    new value — this is what makes presence changes "stick" between snapshot
   *    reloads (fixes G2's "presence frozen at snapshot load" root cause).
   * 3. If the member is under takeover, SKIP the walk. The updated `presence`
   *    field will be picked up by `handleTakeoverEnd` when the player releases
   *    control, and the walk-home there will use the new seat. This respects
   *    player control without fighting it.
   * 4. Otherwise, compute the new home via `computeHomePlacement` (passing the
   *    preferred zone through to `computePlacement`) and kick off a walk via
   *    `devSim.walkHome`. The existing walking_home arrival branch handles
   *    animation, yaw restoration, and locationContext update.
   *
   * @param userId        The member whose presence changed.
   * @param newPresence   The new presence value.
   * @param preferredZone Optional break-zone hint for on_break placements.
   */
  applyPresenceChange(
    userId: string,
    newPresence: PresenceState,
    preferredZone?: string,
  ): void {
    const member = this.state.members.get(userId)
    if (!member) return

    // Idempotent — no walk if nothing changed. Prevents spurious animation
    // restarts on duplicate events (e.g. Slack poll firing the same status
    // twice in a row, or two bridge publishes racing).
    if (member.presence === newPresence) return

    member.presence = newPresence

    // Respect player control. The new presence is stored on the schema, so
    // handleTakeoverEnd will see it when the player releases and walk to the
    // right seat automatically. No server-side fighting with WASD input.
    if (member.takeoverSessionId) return

    const home = this.computeHomePlacement(userId, newPresence, preferredZone)
    this.devSim.walkHome(member, home.x, home.z, home.yaw, home.sitting)
    console.log(
      `[OrgRoom] ${member.name} presence → ${newPresence}, walking to ${home.locationContext}`,
    )
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
    // frozen in the air until the walk-home below takes over on the next tick.
    member.y = 0
    if (member.animState === "jump" || member.animState === "sprint") {
      member.animState = "idle"
    }
    member.takeoverSessionId = ""

    // Walk the character back to its presence-based seat. Without this, the
    // character would freeze wherever the player left them until the next
    // dev_activity or presence event. The existing devSim walking_home state
    // machine handles the animation, yaw restoration, and locationContext
    // update on arrival — see walkHome() for the contract.
    const home = this.computeHomePlacement(
      data.userId,
      member.presence as PresenceState,
    )
    this.devSim.walkHome(member, home.x, home.z, home.yaw, home.sitting)
    console.log(
      `[OrgRoom] ${member.name} takeover END → walking home to ${home.locationContext}`,
    )
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

// ─── Bridge event validators ───────────────────

/** Payload shape published by the backend on Slack presence transitions. */
interface MemberPresenceEvent {
  user_id: string
  presence: PresenceState
}

/**
 * Best-effort runtime validator for the member_presence bridge payload.
 * The backend is in a separate process; cross-process JSON is untrusted
 * at the schema level. Returns `null` on malformed input (caller logs and
 * drops the event). Same defensive pattern as `parseDevActivityEvent` and
 * `parseAgentActivityEvent`.
 */
function parseMemberPresenceEvent(raw: unknown): MemberPresenceEvent | null {
  if (!raw || typeof raw !== "object") return null
  const d = raw as Record<string, unknown>
  if (typeof d.user_id !== "string" || d.user_id.length === 0) return null
  if (
    d.presence !== "active" &&
    d.presence !== "on_break" &&
    d.presence !== "at_home"
  ) return null
  return { user_id: d.user_id, presence: d.presence }
}
