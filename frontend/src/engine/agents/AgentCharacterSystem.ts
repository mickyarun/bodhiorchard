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

export class AgentCharacterSystem {
  private characters = new Map<string, AgentCharacter>()
  private entries = new Map<string, AgentEntry>()
  private parent: pc.Entity | null = null
  private app: Application | null = null
  private loader: AssetLoader | null = null
  private getTreePos: TreePositionLookup = () => null

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

    for (const a of activities) {
      if (a.status === 'completed' || a.status === 'failed') continue
      await this.spawnFromActivity(a)
    }
  }

  /** Handle a live WebSocket event — spawn, update, or remove a robot. */
  async handleLiveEvent(activity: EngineAgentActivity): Promise<void> {
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
    const toRemove: string[] = []
    for (const [key, character] of this.characters) {
      character.update(dt)
      if (character.isDone) {
        character.destroy()
        toRemove.push(key)
        continue
      }

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
