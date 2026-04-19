// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * AgentCharacterSystem — manages agent robot characters in the 3D garden.
 *
 * Each BUDAgentTask = one robot character. Uses task_id as the unique key.
 * Handles multi-repo shuffle (impacted_repo_names), repo-free center positioning,
 * and live event updates from WebSocket.
 *
 * Lifecycle: build() from EngineData → update(dt) per frame → handleLiveEvent() → destroy()
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { AssetLoader } from '../assets/AssetLoader'
import type { EngineAgentActivity } from '../types'
import { AgentCharacter } from './AgentCharacter'

const TREE_OFFSET_X = 1.5
const TREE_OFFSET_Z = 1.5
const STACK_OFFSET = 1.2

/** Tracked state for one active agent robot. */
interface AgentEntry {
  key: string
  skillSlug: string
  action: string
  repoNames: string[]
  currentRepoIndex: number
  shuffleTimer: number
}

/** Position lookup function provided by SceneManager. */
export type TreePositionLookup = (repoName: string) => pc.Vec3 | null

/** Snapshot of a server-authoritative agent from OrgRoomState (Phase 6). */
export interface AgentSnapshot {
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
  state: string      // spawning | working | walking | completing | done
  action: string     // grab | spin | miniguns | '' (idle)
  message: string
}

export class AgentCharacterSystem {
  private characters = new Map<string, AgentCharacter>()
  private entries = new Map<string, AgentEntry>()
  private parent: pc.Entity | null = null
  private app: Application | null = null
  private loader: AssetLoader | null = null
  private getTreePos: TreePositionLookup = () => null

  // Phase 6: when true, positions + lifecycle are driven by OrgRoomClient snapshots
  // and the local wandering/working simulation is disabled.
  private serverDriven = false
  // Per-key generation counter. Every spawn or remove bumps the counter for
  // that key; an in-flight spawn compares its captured generation against the
  // current value and aborts if another call superseded it. This prevents a
  // stale spawn from "winning" after a remove-then-respawn sequence.
  private spawnGen = new Map<string, number>()

  /** Build from initial data (page load). */
  async build(
    app: Application,
    loader: AssetLoader,
    activities: EngineAgentActivity[],
    getTreePosition: TreePositionLookup,
  ): Promise<void> {
    this.app = app
    this.loader = loader
    this.getTreePos = getTreePosition

    this.parent = new pc.Entity('AgentCharacters')
    app.root.addChild(this.parent)

    // In server-driven mode, OrgRoomClient will call spawnFromAgentSnapshot
    // for every existing agent on connect — skip the initial spawns here.
    if (this.serverDriven) return

    for (const a of activities) {
      if (a.status === 'completed' || a.status === 'failed') continue
      await this.spawnFromActivity(a)
    }
  }

  /**
   * Toggle server-driven mode. When enabled, all spawn/update/remove traffic
   * comes from OrgRoomClient callbacks; local handleLiveEvent and update
   * wandering logic are suppressed.
   */
  setServerDriven(enabled: boolean): void {
    this.serverDriven = enabled
  }

  /** Handle a live WebSocket event — spawn, update, or remove a robot. */
  async handleLiveEvent(activity: EngineAgentActivity): Promise<void> {
    // Server-driven mode: ignore legacy WebSocket events — OrgRoom snapshots
    // are the authoritative source.
    if (this.serverDriven) return
    const key = this.getKey(activity)

    if (activity.event_type === 'skill_completed' || activity.event_type === 'skill_failed') {
      const character = this.characters.get(key)
      if (character) character.complete()
      this.entries.delete(key)
      return
    }

    if (activity.event_type === 'skill_invoked' || activity.status === 'in_progress') {
      if (!this.characters.has(key)) {
        await this.spawnFromActivity(activity)
      } else {
        // Update action text
        const character = this.characters.get(key)
        character?.updateAction(this.formatAction(activity))
      }
    }
  }

  /** Per-frame update — animations, wandering, and lifecycle. */
  update(dt: number): void {
    // Server-driven mode: the server owns walk/work cycles. We still run
    // per-character update() for visual animations (spaceship, drop, hop,
    // fade), but suppress the wandering scheduler since targets are chosen
    // server-side and arrive via snapshot updates.
    const toRemove: string[] = []
    for (const [key, character] of this.characters) {
      character.update(dt)
      if (character.isDone) {
        character.destroy()
        toRemove.push(key)
        continue
      }

      if (this.serverDriven) continue

      // Drive wandering — when working timer expires, walk to next tree
      if (character.readyToWalk) {
        const entry = this.entries.get(key)
        if (entry && entry.repoNames.length > 1) {
          // Multi-repo: walk to next repo tree in sequence
          entry.currentRepoIndex = (entry.currentRepoIndex + 1) % entry.repoNames.length
          const pos = this.getPosition(entry)
          if (pos) character.startWalking(pos.x, pos.z)
        } else if (entry) {
          // Single-repo or repo-free: wander in small patrol radius
          const basePos = this.getPosition(entry)
          const cx = basePos?.x ?? 0  // center for repo-free agents
          const cz = basePos?.z ?? 0
          const angle = Math.random() * Math.PI * 2
          const radius = 1.5 + Math.random() * 2.0
          character.startWalking(cx + Math.cos(angle) * radius, cz + Math.sin(angle) * radius)
        }
      }
    }
    for (const id of toRemove) this.characters.delete(id)
  }

  // ─── Server-driven (Phase 6) ────────────────

  /**
   * Spawn a character from a server snapshot. Idempotent — duplicate
   * adds (or races during async load) are ignored via a per-key generation
   * counter that any concurrent remove/re-add will bump.
   */
  async spawnFromAgentSnapshot(snapshot: AgentSnapshot): Promise<void> {
    if (!this.parent || !this.loader || !this.app) return
    const key = snapshot.agentId
    if (this.characters.has(key)) return

    const myGen = (this.spawnGen.get(key) ?? 0) + 1
    this.spawnGen.set(key, myGen)

    const character = new AgentCharacter(key, snapshot.skillSlug)
    await character.spawn(this.parent, this.loader, this.app, snapshot.x, snapshot.z, snapshot.message)

    // Another spawn/remove superseded us while awaiting asset load — discard.
    if (this.spawnGen.get(key) !== myGen) {
      character.destroy()
      return
    }
    this.characters.set(key, character)
    this.applySnapshot(character, snapshot)
  }

  /** Apply a position/state/message delta from a server snapshot. */
  updateFromAgentSnapshot(snapshot: AgentSnapshot): void {
    const character = this.characters.get(snapshot.agentId)
    if (!character) return
    this.applySnapshot(character, snapshot)
  }

  /** Remove a character by agentId (server-driven despawn). */
  removeByAgentId(agentId: string): void {
    // Bump the generation so any in-flight spawn for this id aborts on return
    this.spawnGen.set(agentId, (this.spawnGen.get(agentId) ?? 0) + 1)
    const character = this.characters.get(agentId)
    if (!character) return
    // Play completion flourish then let update() clean up via isDone
    character.complete()
  }

  private applySnapshot(character: AgentCharacter, snapshot: AgentSnapshot): void {
    // Position: write directly to wrapper (the server owns x/z; local visuals
    // like hop/drop add small y offsets we don't want to stomp).
    const wrapper = character.getWrapper()
    if (wrapper) {
      const current = wrapper.getPosition()
      wrapper.setPosition(snapshot.x, current.y, snapshot.z)
      wrapper.setEulerAngles(0, snapshot.yaw, 0)
    }
    // Label text — update whenever the server sends a new message
    if (snapshot.message) character.updateAction(snapshot.message)
    // Completion signal
    if (snapshot.state === 'completing' || snapshot.state === 'done') {
      character.complete()
    }
  }

  /** Get all agent character wrapper entities for picking. */
  getPickableEntities(): pc.Entity[] {
    const entities: pc.Entity[] = []
    for (const character of this.characters.values()) {
      const wrapper = character.getWrapper()
      if (wrapper) entities.push(wrapper)
    }
    return entities
  }

  /** Forward a click event to the agent character for greeting animation. */
  handleAgentClick(agentKey: string): void {
    for (const character of this.characters.values()) {
      if (character.key === agentKey) {
        character.onClicked()
        break
      }
    }
  }

  destroy(): void {
    for (const character of this.characters.values()) character.destroy()
    this.characters.clear()
    this.entries.clear()
    this.parent?.destroy()
    this.parent = null
  }

  // ─── Private helpers ────────────────────────

  private async spawnFromActivity(a: EngineAgentActivity): Promise<void> {
    if (!this.parent || !this.loader || !this.app) return
    const key = this.getKey(a)
    if (this.characters.has(key)) return

    // Build repo list: prefer impacted_repo_names, fall back to single repo_name
    const repoNames = a.impacted_repo_names.length > 0
      ? [...a.impacted_repo_names]
      : a.repo_name ? [a.repo_name] : []

    const entry: AgentEntry = {
      key,
      skillSlug: a.skill_slug || 'agent',
      action: this.formatAction(a),
      repoNames,
      currentRepoIndex: 0,
      shuffleTimer: 0,
    }
    this.entries.set(key, entry)

    const pos = this.getPosition(entry)
    // Repo-free agents: spawn near the orchard but offset to a clear area
    // (center 0,0 has trees/rocks — offset to the path between zones)
    const x = pos?.x ?? 5
    const z = pos?.z ?? 5

    const character = new AgentCharacter(key, entry.skillSlug)
    await character.spawn(this.parent, this.loader, this.app, x, z, entry.action)
    this.characters.set(key, character)
  }

  private getKey(a: EngineAgentActivity): string {
    // Prefer task_id (unique per BUDAgentTask), fall back to session/slug
    return a.task_id || a.session_id || `${a.skill_slug}_${a.agent_name}_${a.timestamp}`
  }

  private formatAction(a: EngineAgentActivity): string {
    if (a.bud_title && a.bud_number) return `BUD #${a.bud_number}: ${a.action}`
    if (a.bud_number) return `BUD #${a.bud_number}: ${a.action}`
    return a.action
  }

  private getPosition(entry: AgentEntry): { x: number; z: number } | null {
    if (entry.repoNames.length === 0) return null  // repo-free → caller uses (0,0)

    const repoName = entry.repoNames[entry.currentRepoIndex]
    const treePos = this.getTreePos(repoName)
    if (!treePos) return null

    const stackIndex = this.getStackIndex(repoName, entry.key)
    return {
      x: treePos.x + TREE_OFFSET_X + stackIndex * STACK_OFFSET,
      z: treePos.z + TREE_OFFSET_Z,
    }
  }

  private getStackIndex(repoName: string, key: string): number {
    let index = 0
    for (const [entryKey, entry] of this.entries) {
      if (entryKey === key) return index
      const currentRepo = entry.repoNames[entry.currentRepoIndex]
      if (currentRepo === repoName && this.characters.has(entryKey)) index++
    }
    return index
  }
}
