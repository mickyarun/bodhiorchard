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
 * AgentActivitySim — server-side simulation of agent/robot movements.
 *
 * Ported from `frontend/src/engine/agents/AgentCharacterSystem.ts` and the
 * logical (non-visual) parts of `AgentCharacter.ts`. The server owns:
 *   - Spawn position (near first repo tree or fallback)
 *   - Walk/work cycle between repo trees
 *   - Working phrase cycling
 *   - Completion/failure → transition to "completing" → "done" → despawn
 *
 * The frontend is responsible for visual-only flourishes (spaceship fly-in,
 * drop animation, hop, fade, greeting) that don't affect logical position.
 *
 * Lifecycle state machine:
 *   spawning → working → walking → working → ... → completing → done
 */
import { MapSchema } from "@colyseus/schema"
import { AgentState } from "../schema/AgentState"
import { safeLog } from "../bridge/logSanitize"
import { getAgentSlotAtTree, getAgentFallbackSlot } from "./WorldLayout"
import { countAgentsAtRepo } from "../../../shared/world/agentStacking"
import {
  PHRASES,
  DEFAULT_PHRASES,
  getSkillDisplayName,
} from "../../../shared/agents/AgentPhrases"

// ─── Constants (mirror frontend AgentCharacter) ─────────

const WALK_SPEED = 1.5              // units/sec
const ARRIVE_DIST_SQ = 2.25         // 1.5^2
const WORK_DURATION_MIN = 6         // seconds
const WORK_DURATION_MAX = 12
const PHRASE_INTERVAL = 4           // seconds between label phrase updates
const SPAWN_ANIM_SEC = 2.5          // spawn → working transition delay
const COMPLETE_PAUSE_SEC = 2.0      // completing → done delay
const ACTION_CYCLE_SEC = 4          // cycle action (grab/spin/miniguns) every N sec
const ACTION_CYCLE: Array<"grab" | "spin" | "miniguns"> = [
  "grab", "spin", "miniguns", "grab", "miniguns", "spin",
]

// ─── Types ─────────────────────────────────

type AgentMoveState = "spawning" | "working" | "walking" | "completing" | "done"

/** Per-agent simulation state tracked alongside the schema AgentState. */
interface AgentEntry {
  key: string
  skillSlug: string
  actorName: string
  repoNames: string[]
  currentRepoIndex: number
  stackIndex: number     // frozen at spawn time — stable even as siblings complete
  moveState: AgentMoveState
  stateTimer: number
  phraseTimer: number
  workDuration: number
  phraseIndex: number
  targetX: number
  targetZ: number
  budNumber: number
  action: string         // current action text (e.g., "BUD #12: Analyzing")
  pendingComplete: boolean
}

/** An agent activity event from the backend bridge. */
export interface AgentActivityEvent {
  task_id: string | null
  session_id: string | null
  skill_slug: string | null
  actor_name: string | null
  event_type: string           // skill_invoked, skill_completed, skill_failed, tool_call, etc.
  status: string               // in_progress, completed, failed
  message: string | null
  repo_name: string | null
  impacted_repo_names: string[]
  bud_number: number | null
  bud_title: string | null
}

/**
 * Best-effort runtime validator for cross-process agent activity payloads.
 * Returns null on malformed input (dropped + logged by caller).
 */
export function parseAgentActivityEvent(raw: unknown): AgentActivityEvent | null {
  if (!raw || typeof raw !== "object") return null
  const d = raw as Record<string, unknown>
  if (typeof d.event_type !== "string") return null
  if (typeof d.status !== "string") return null
  const s = (v: unknown): string | null =>
    typeof v === "string" ? v : null
  const n = (v: unknown): number | null =>
    typeof v === "number" && isFinite(v) ? v : null
  const arr = (v: unknown): string[] =>
    Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []
  return {
    task_id:             s(d.task_id),
    session_id:          s(d.session_id),
    skill_slug:          s(d.skill_slug),
    actor_name:          s(d.actor_name),
    event_type:          d.event_type,
    status:              d.status,
    message:             s(d.message),
    repo_name:           s(d.repo_name),
    impacted_repo_names: arr(d.impacted_repo_names),
    bud_number:          n(d.bud_number),
    bud_title:           s(d.bud_title),
  }
}

// ─── Sim ───────────────────────────────────

export class AgentActivitySim {
  private entries = new Map<string, AgentEntry>()

  /**
   * @param repoPositions Tree position registry owned by OrgRoom. The sim
   *   reads from it on every event/tick — OrgRoom mutates in place (clear + set)
   *   on snapshot reload.
   */
  constructor(private repoPositions: Map<string, { x: number; z: number }>) {}

  /** Drop all tracked agent entries. Called on snapshot reload. */
  reset(agents: MapSchema<AgentState>): void {
    this.entries.clear()
    agents.clear()
  }

  /**
   * Handle an agent activity event from the bridge. Spawns, updates, or
   * despawns agents as appropriate. Mutates the schema map directly.
   */
  handleEvent(agents: MapSchema<AgentState>, event: AgentActivityEvent): void {
    const key = this.getKey(event)
    if (!key) return

    // Completion / failure → begin despawn sequence
    if (event.event_type === "skill_completed" || event.event_type === "skill_failed") {
      // Direct key hit is the happy path: same task_id / session_id /
      // fallback key across the agent's whole lifecycle.
      const direct = this.entries.get(key)
      if (direct) {
        this.dispatchComplete(agents, direct)
        return
      }
      // Orphan sweep: when the first event(s) for a skill arrive without
      // a ``task_id`` they spawn an agent under the fallback key
      // ``${skill_slug}_${actor_name}``. Once the backend resolves the
      // task_id, every subsequent event keys differently — including the
      // ``skill_completed`` — and the original entry becomes an undead
      // robot stuck "Reviewing imports…" forever. Match on the structural
      // identity (skill_slug + actor_name + bud_number) and despawn every
      // matching entry. Cleans up duplicates created by any keying drift,
      // not just the task_id-late scenario.
      const slug = event.skill_slug ?? ""
      const actor = event.actor_name ?? ""
      const bud = event.bud_number ?? 0
      let swept = 0
      for (const candidate of this.entries.values()) {
        if (
          candidate.skillSlug === slug &&
          candidate.actorName === actor &&
          candidate.budNumber === bud
        ) {
          this.dispatchComplete(agents, candidate)
          swept += 1
        }
      }
      if (swept > 0) {
        this.logOrphanSweep(bud, swept)
      }
      return
    }

    // skill_invoked or any in_progress update → spawn or update
    if (event.event_type === "skill_invoked" || event.status === "in_progress") {
      const entry = this.entries.get(key) ?? this.spawn(agents, key, event)
      // Update action text
      entry.action = this.formatAction(event)
      const agent = agents.get(key)
      if (agent) {
        agent.message = entry.action
        agent.actorName = event.actor_name ?? agent.actorName
      }
    }
  }

  /** Per-frame tick — spawn delay, work timers, walking, phrase cycles, despawn. */
  tick(agents: MapSchema<AgentState>, dt: number): void {
    for (const [key, entry] of this.entries) {
      const agent = agents.get(key)
      if (!agent) {
        this.entries.delete(key)
        continue
      }

      entry.stateTimer += dt

      switch (entry.moveState) {
        case "spawning":
          if (entry.stateTimer >= SPAWN_ANIM_SEC) {
            if (entry.pendingComplete) {
              entry.pendingComplete = false
              this.beginCompleting(agents, entry)
            } else {
              this.enterWorking(agent, entry)
            }
          }
          break

        case "working":
          entry.phraseTimer += dt
          // Cycle action animation hint (client renders it)
          {
            const cycleIdx = Math.floor(entry.stateTimer / ACTION_CYCLE_SEC) % ACTION_CYCLE.length
            const nextAction = ACTION_CYCLE[cycleIdx]
            if (agent.action !== nextAction) agent.action = nextAction
          }
          // Cycle label phrase
          if (entry.phraseTimer >= PHRASE_INTERVAL) {
            entry.phraseTimer = 0
            const phrase = this.nextPhrase(entry)
            agent.message = phrase
          }
          // Done working at this tree → pick next destination
          if (entry.stateTimer >= entry.workDuration) {
            this.pickNextTarget(agent, entry)
          }
          break

        case "walking":
          this.tickWalking(agent, entry, dt)
          break

        case "completing":
          if (entry.stateTimer >= COMPLETE_PAUSE_SEC) {
            entry.moveState = "done"
            agent.state = "done"
            // Remove from schema (client will fade out via onRemove)
            agents.delete(key)
            this.entries.delete(key)
          }
          break

        case "done":
          // Belt-and-suspenders cleanup
          agents.delete(key)
          this.entries.delete(key)
          break
      }
    }
  }

  // ─── Internal helpers ──────────────────

  private spawn(
    agents: MapSchema<AgentState>,
    key: string,
    event: AgentActivityEvent,
  ): AgentEntry {
    const repoNames = event.impacted_repo_names.length > 0
      ? [...event.impacted_repo_names]
      : (event.repo_name ? [event.repo_name] : [])

    // Freeze the stack index at spawn time so sibling completions don't make
    // this agent's target jump sideways when its own next target is recomputed.
    const firstRepo = repoNames[0] ?? ""
    const stackIndex = firstRepo
      ? countAgentsAtRepo(this.entries.values(), firstRepo)
      : 0

    const entry: AgentEntry = {
      key,
      skillSlug:       event.skill_slug ?? "agent",
      actorName:       event.actor_name ?? "",
      repoNames,
      currentRepoIndex: 0,
      stackIndex,
      moveState:       "spawning",
      stateTimer:      0,
      phraseTimer:     0,
      workDuration:    this.randomWorkDuration(),
      phraseIndex:     0,
      targetX:         0,
      targetZ:         0,
      budNumber:       event.bud_number ?? 0,
      action:          this.formatAction(event),
      pendingComplete: false,
    }

    // Compute spawn position — first tree with offset, or orchard-anchored fallback
    const pos = this.getRepoPosition(entry) ?? getAgentFallbackSlot()
    entry.targetX = pos.x
    entry.targetZ = pos.z

    const agent = new AgentState()
    agent.agentId = key
    agent.skillSlug = entry.skillSlug
    agent.skillName = getSkillDisplayName(entry.skillSlug)
    agent.actorName = entry.actorName
    agent.repoName = entry.repoNames[0] ?? ""
    agent.budNumber = entry.budNumber
    agent.x = pos.x
    agent.y = 0
    agent.z = pos.z
    agent.yaw = 0
    agent.state = "spawning"
    agent.action = ""
    agent.message = entry.action
    agents.set(key, agent)

    this.entries.set(key, entry)
    return entry
  }

  private enterWorking(agent: AgentState, entry: AgentEntry): void {
    entry.moveState = "working"
    entry.stateTimer = 0
    entry.phraseTimer = 0
    entry.workDuration = this.randomWorkDuration()
    agent.state = "working"
    agent.message = this.nextPhrase(entry)
  }

  private pickNextTarget(agent: AgentState, entry: AgentEntry): void {
    if (entry.repoNames.length > 1) {
      // Multi-repo: walk to next tree in sequence
      entry.currentRepoIndex = (entry.currentRepoIndex + 1) % entry.repoNames.length
      const pos = this.getRepoPosition(entry)
      if (pos) {
        entry.targetX = pos.x
        entry.targetZ = pos.z
        this.beginWalking(agent, entry)
        return
      }
    }
    // Repo-free: no tree to patrol around. Stay put at the fallback slot —
    // wandering from there with radius 3.5 can reach the bodhi mound
    // (FALLBACK_HUB_OFFSET 4.8 − 3.5 = 1.3 < MOUND_RADIUS 4.0), which
    // would visibly clip the robot into the platform.
    if (entry.repoNames.length === 0) {
      this.enterWorking(agent, entry)
      return
    }
    // Single-repo: wander within a small patrol radius of the tree slot.
    // Anchoring to `agent.x/z` here caused unbounded drift pre-fix.
    const basePos = this.getRepoPosition(entry) ?? getAgentFallbackSlot()
    const angle = Math.random() * Math.PI * 2
    const radius = 1.5 + Math.random() * 2.0
    entry.targetX = basePos.x + Math.cos(angle) * radius
    entry.targetZ = basePos.z + Math.sin(angle) * radius
    this.beginWalking(agent, entry)
  }

  private beginWalking(agent: AgentState, entry: AgentEntry): void {
    entry.moveState = "walking"
    entry.stateTimer = 0
    agent.state = "walking"
    agent.action = ""
    const currentRepo = entry.repoNames[entry.currentRepoIndex]
    if (currentRepo) agent.repoName = currentRepo
  }

  private tickWalking(agent: AgentState, entry: AgentEntry, dt: number): void {
    const dx = entry.targetX - agent.x
    const dz = entry.targetZ - agent.z
    const distSq = dx * dx + dz * dz

    if (distSq < ARRIVE_DIST_SQ) {
      this.enterWorking(agent, entry)
      return
    }

    const dist = Math.sqrt(distSq)
    const step = WALK_SPEED * dt
    const nx = dx / dist
    const nz = dz / dist
    agent.x = agent.x + nx * step
    agent.y = 0  // ground-pinned (client adds hop/drop visuals on top)
    agent.z = agent.z + nz * step
    // Face walking direction (matches PlayCanvas yaw convention used elsewhere)
    agent.yaw = (Math.atan2(nx, nz) * 180) / Math.PI
  }

  private beginCompleting(agents: MapSchema<AgentState>, entry: AgentEntry): void {
    entry.moveState = "completing"
    entry.stateTimer = 0
    const agent = agents.get(entry.key)
    if (agent) {
      agent.state = "completing"
      agent.action = ""
      agent.message = "Task Complete!"
    }
  }

  /**
   * Wrap ``beginCompleting`` with the "still spawning?" check so both the
   * direct-key and orphan-sweep callers go through the same gate. If the
   * entry is mid-spawn the completion is queued via ``pendingComplete``
   * so the spawn animation finishes cleanly before the despawn starts.
   */
  private dispatchComplete(agents: MapSchema<AgentState>, entry: AgentEntry): void {
    if (entry.moveState === "spawning") {
      entry.pendingComplete = true
      return
    }
    this.beginCompleting(agents, entry)
  }

  /**
   * Diagnostic log for the orphan-sweep path. Numbers only — the
   * sweep itself happens whether or not we log it, and the count is
   * sufficient to confirm "the cleanup fired N times". Dropping the
   * skill/actor names eliminates the only user-controlled flow into
   * the log call, which is what CodeQL's per-flow analyser kept
   * tracking through the orphan-match for-loop comparison even when
   * the values were wrapped in ``safeLog``. The skill/actor that
   * triggered the sweep are still visible in the upstream backend
   * ``agent_activity_recorded`` log line.
   */
  private logOrphanSweep(budNumber: number, sweptCount: number): void {
    console.log(
      "[AgentActivitySim] orphan_sweep bud=%d swept=%d",
      budNumber,
      sweptCount,
    )
  }

  private getRepoPosition(entry: AgentEntry): { x: number; z: number } | null {
    if (entry.repoNames.length === 0) return null
    const repo = entry.repoNames[entry.currentRepoIndex]
    const tree = this.repoPositions.get(repo)
    if (!tree) return null
    return getAgentSlotAtTree(tree, entry.stackIndex)
  }

  private randomWorkDuration(): number {
    return WORK_DURATION_MIN + Math.random() * (WORK_DURATION_MAX - WORK_DURATION_MIN)
  }

  private nextPhrase(entry: AgentEntry): string {
    const list = PHRASES[entry.skillSlug] ?? DEFAULT_PHRASES
    const phrase = list[entry.phraseIndex % list.length]
    entry.phraseIndex++
    return phrase
  }

  private getKey(event: AgentActivityEvent): string | null {
    // Preserved from the frontend AgentCharacterSystem — if the first event
    // for a skill arrives without task_id (session context only) and a later
    // event has task_id resolved, the two are keyed differently and the first
    // entry becomes an orphan. Ensure the backend always emits task_id on
    // skill lifecycle events to avoid this drift.
    return event.task_id
      ?? event.session_id
      ?? (event.skill_slug ? `${event.skill_slug}_${event.actor_name ?? "unknown"}` : null)
  }

  private formatAction(event: AgentActivityEvent): string {
    const base = event.message ?? event.event_type
    if (event.bud_number) return `BUD #${event.bud_number}: ${base}`
    return base
  }
}
