/**
 * DevActivitySim — server-side simulation of dev activity movements.
 *
 * Ported from `frontend/src/engine/characters/CharacterSystem.ts`.
 *
 * When a dev_activity event arrives (via bridge), the simulation:
 *   1. Walks the member's character to their repo tree
 *   2. Shows a label ("Coding...", "Editing X.ts", etc.) above their head
 *   3. Cycles label phrases every 5s while working
 *   4. Returns the member to their original seat on session_end or timeout (60s idle)
 *
 * Per-frame tick updates positions at the server's simulation interval.
 */
import type { MemberState } from "../schema/MemberState"

// ─── Constants (mirror frontend) ──────────────

const WALK_SPEED = 1.2
const ARRIVE_DIST_SQ = 1.0
const IDLE_TIMEOUT = 60          // seconds before auto-return
const TREE_OFFSET_X = -1.5       // opposite side from agent robots
const TREE_OFFSET_Z = 1.0
const ORCHARD_FALLBACK_X = -3.0
const ORCHARD_FALLBACK_Z = 3.0
const PHRASE_INTERVAL = 5        // seconds between phrase cycles

const WORKING_PHRASES = [
  "Coding...", "Writing code...", "Debugging...", "Refactoring...",
  "Reviewing changes...", "Running tests...", "Thinking...",
  "Reading docs...", "Fixing a bug...", "Adding feature...",
]

type MoveState = "idle" | "walking_to_tree" | "working" | "walking_home"

/** Per-member activity state tracked by the simulation. */
interface ActivityState {
  userId: string
  displayName: string
  originalX: number
  originalZ: number
  originalYaw: number
  wasSitting: boolean
  currentRepoName: string | null
  targetX: number
  targetZ: number
  moveState: MoveState
  idleTimer: number
  phraseTimer: number
}

/** A dev activity event from the backend bridge. */
export interface DevActivityEvent {
  user_id: string | null   // null when the backend can't resolve an MCP-token user
  actor_name: string | null
  event_type: string       // session_start, session_end, commit, file_change, tool_call, etc.
  status: string           // in_progress, completed, failed
  message: string | null
  repo_name: string | null
  file_path: string | null
}

/**
 * Best-effort runtime validator for cross-process bridge payloads.
 * The backend is in a separate process and may drift; this catches
 * malformed events before they reach the sim. Returns null on failure.
 */
export function parseDevActivityEvent(raw: unknown): DevActivityEvent | null {
  if (!raw || typeof raw !== "object") return null
  const d = raw as Record<string, unknown>
  if (typeof d.event_type !== "string") return null
  if (typeof d.status !== "string") return null
  const strOrNull = (v: unknown): string | null =>
    typeof v === "string" ? v : v == null ? null : null
  return {
    user_id:    strOrNull(d.user_id),
    actor_name: strOrNull(d.actor_name),
    event_type: d.event_type,
    status:     d.status,
    message:    strOrNull(d.message),
    repo_name:  strOrNull(d.repo_name),
    file_path:  strOrNull(d.file_path),
  }
}

export class DevActivitySim {
  private activeDevs = new Map<string, ActivityState>()

  /**
   * @param repoPositions Tree positions from the repo registry. The sim
   *   holds this reference and reads from it on each event — the owner
   *   (OrgRoom) is expected to mutate the Map in place (clear + set)
   *   on snapshot reload rather than replacing the instance.
   */
  constructor(private repoPositions: Map<string, { x: number; z: number }>) {}

  /**
   * Drop all tracked activity state. Called on snapshot reload so that
   * preserved `originalX/Z/wasSitting` don't point to stale desks after
   * house-grid reassignment. Members mid-walk will lose their "in-flight"
   * walk state; the next bridge event re-seats them against fresh positions.
   */
  reset(): void {
    this.activeDevs.clear()
  }

  /**
   * Handle a dev activity event — update label, start walking, or return to seat.
   * Mutates the member's MemberState directly.
   */
  handleEvent(
    members: Map<string, MemberState>,
    event: DevActivityEvent,
  ): void {
    const member = this.findMember(members, event.user_id, event.actor_name)
    if (!member) return

    // Skip for player-controlled characters
    if (member.takeoverSessionId) return

    // Session end or completion → return to seat
    if (
      event.event_type === "session_end" ||
      event.status === "completed" ||
      event.status === "failed"
    ) {
      this.returnToSeat(member)
      return
    }

    // Get or create activity state
    let state = this.activeDevs.get(member.userId)
    if (!state) {
      state = {
        userId:         member.userId,
        displayName:    event.actor_name ?? member.name,
        originalX:      member.x,
        originalZ:      member.z,
        originalYaw:    member.yaw,
        wasSitting:     member.animState === "sit",
        currentRepoName: null,
        targetX:        member.x,
        targetZ:        member.z,
        moveState:      "idle",
        idleTimer:      0,
        phraseTimer:    0,
      }
      this.activeDevs.set(member.userId, state)
    }

    // Update label text
    state.displayName = event.actor_name ?? member.name
    member.labelName = state.displayName
    member.labelMessage = formatMessage(event)
    state.idleTimer = 0

    // If repo changed, walk to that tree
    if (event.repo_name && event.repo_name !== state.currentRepoName) {
      const treePos = this.repoPositions.get(event.repo_name)
      if (treePos) {
        state.currentRepoName = event.repo_name
        state.targetX = treePos.x + TREE_OFFSET_X
        state.targetZ = treePos.z + TREE_OFFSET_Z
        state.moveState = "walking_to_tree"
        member.animState = "walk"
        member.locationContext = `tree_${event.repo_name}`
      } else {
        this.walkToOrchardFallback(state, member)
      }
    } else if (!event.repo_name && state.moveState === "idle") {
      this.walkToOrchardFallback(state, member)
    }
  }

  /** Per-frame tick — advance walking, cycle phrases, handle timeouts. */
  tick(members: Map<string, MemberState>, dt: number): void {
    for (const [userId, state] of this.activeDevs) {
      const member = members.get(userId)
      if (!member) {
        this.activeDevs.delete(userId)
        continue
      }
      // Skip if taken over by a player (client drives position)
      if (member.takeoverSessionId) continue

      switch (state.moveState) {
        case "walking_to_tree":
          this.tickWalking(member, state, dt, "working")
          break

        case "working": {
          state.idleTimer += dt
          state.phraseTimer += dt

          if (state.phraseTimer >= PHRASE_INTERVAL) {
            state.phraseTimer = 0
            const phrase = WORKING_PHRASES[
              Math.floor(Math.random() * WORKING_PHRASES.length)
            ]
            member.labelMessage = phrase
          }

          if (state.idleTimer >= IDLE_TIMEOUT) {
            this.returnToSeat(member)
          }
          break
        }

        case "walking_home": {
          const arrived = this.tickWalking(member, state, dt, "idle")
          if (arrived) {
            // Restore original facing (tickWalking left yaw pointing along the
            // last walk vector). animState was already set by tickWalking.
            member.yaw = state.originalYaw
            member.labelName = ""
            member.labelMessage = ""
            // Arrived at seat → update locationContext so interior visitors
            // now see the owner NPC (see C5 in Code Review 4).
            member.locationContext = `house_${member.userId}`
            this.activeDevs.delete(userId)
          }
          break
        }
      }
    }
  }

  // ─── Internal helpers ────────────────────────

  private tickWalking(
    member: MemberState,
    state: ActivityState,
    dt: number,
    arrivalState: MoveState,
  ): boolean {
    const dx = state.targetX - member.x
    const dz = state.targetZ - member.z
    const distSq = dx * dx + dz * dz

    if (distSq < ARRIVE_DIST_SQ) {
      state.moveState = arrivalState
      member.animState = arrivalState === "working" ? "idle" : (state.wasSitting ? "sit" : "idle")
      return true
    }

    const dist = Math.sqrt(distSq)
    const step = WALK_SPEED * dt
    const nx = dx / dist
    const nz = dz / dist
    member.x = member.x + nx * step
    member.y = 0  // mirror frontend: ground-pinned while walking
    member.z = member.z + nz * step
    member.yaw = (Math.atan2(nx, nz) * 180) / Math.PI
    member.animState = "walk"
    return false
  }

  private returnToSeat(member: MemberState): void {
    const state = this.activeDevs.get(member.userId)
    if (!state) return
    state.targetX = state.originalX
    state.targetZ = state.originalZ
    state.moveState = "walking_home"
    state.currentRepoName = null
    member.animState = "walk"
    // Stay in "garden" while walking home — locationContext only becomes
    // `house_{userId}` once the member arrives (see walking_home arrival
    // branch in tick()). This prevents interior visitors from seeing a
    // phantom owner NPC sitting at the desk while the real character is
    // still walking through the orchard.
    member.locationContext = "garden"
  }

  private walkToOrchardFallback(state: ActivityState, member: MemberState): void {
    state.currentRepoName = null
    state.targetX = ORCHARD_FALLBACK_X + (Math.random() - 0.5) * 3
    state.targetZ = ORCHARD_FALLBACK_Z + (Math.random() - 0.5) * 3
    state.moveState = "walking_to_tree"
    member.animState = "walk"
    member.locationContext = "garden"
  }

  /** Find a member by user_id, falling back to actor_name. */
  private findMember(
    members: Map<string, MemberState>,
    userId: string | null,
    actorName: string | null,
  ): MemberState | undefined {
    if (userId) {
      const m = members.get(userId)
      if (m) return m
    }
    if (actorName) {
      const lower = actorName.toLowerCase()
      let match: MemberState | undefined
      members.forEach(m => {
        if (!match && m.name.toLowerCase() === lower) match = m
      })
      return match
    }
    return undefined
  }
}

/** Format a dev activity event into a short human-readable label message. */
function formatMessage(event: DevActivityEvent): string {
  const msg = event.message
  switch (event.event_type) {
    case "commit":
      return msg
        ? msg.length > 40 ? msg.slice(0, 37) + "..." : msg
        : "Committing..."
    case "file_change":
      if (event.file_path) {
        const parts = event.file_path.split("/")
        return `Editing ${parts[parts.length - 1]}`
      }
      return msg ?? "Editing files..."
    case "session_start":
      return "Starting session..."
    case "session_end":
      return "Session ended"
    case "tool_call":
      return msg ?? "Running tool..."
    case "tool_error":
    case "api_error":
      return msg ?? "Error encountered"
    default:
      return msg ?? "Working..."
  }
}
