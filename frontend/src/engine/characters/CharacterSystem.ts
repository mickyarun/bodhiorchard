/**
 * CharacterSystem — Manages all character entities in the scene.
 *
 * Creates one character per member, places them based on presence:
 *   - 'active' or undefined → seated at a building (desk, coffee bar, etc.)
 *   - 'on_break' → at pool or coffee bar seats
 *   - 'at_home' → at their house bed position
 *
 * Live dev activity: when a developer starts coding (session_start, commit, etc.),
 * their character walks to the repo tree and shows a live activity label above
 * their head (reusing AgentLabel with green tint). On session_end or idle timeout,
 * the character returns to their original seat.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { AssetLoader } from '../assets/AssetLoader'
import type { EngineMember, EngineDevActivity } from '../types'
import type { InteractionPoint } from './InteractionPoint'
import { CharacterFactory, type CharacterEntity } from './CharacterFactory'
import { KayKitCharacterFactory, getClonedMaterials } from './KayKitCharacterFactory'
import { parseCharacterModel, isKayKitConfig } from './CharacterConfig'
import type { HouseResult } from '../buildings/HouseBuilder'
import { AgentLabel } from '../agents/AgentLabel'
import { createLevelBadge } from './LevelBadge'
import { disposeMaterial } from '../utils/EntityUtils'
import type { TreePositionLookup } from '../agents/AgentCharacterSystem'

// ─── Dev activity constants ────────────────────
const DEV_WALK_SPEED = 1.2
const DEV_ARRIVE_DIST_SQ = 1.0
const DEV_IDLE_TIMEOUT = 60         // seconds before auto-return to seat
const DEV_TREE_OFFSET_X = -1.5      // opposite side from agent robots
const DEV_TREE_OFFSET_Z = 1.0
const DEV_LABEL_HEIGHT = 1.55       // above the name label (character height ~0.95)
const DEV_ORCHARD_FALLBACK_X = -3.0 // fallback position when repo_name is null
const DEV_ORCHARD_FALLBACK_Z = 3.0
const DEV_PHRASE_INTERVAL = 5       // seconds between phrase changes while working
const DEV_WORKING_PHRASES = [
  'Coding...', 'Writing code...', 'Debugging...', 'Refactoring...',
  'Reviewing changes...', 'Running tests...', 'Thinking...',
  'Reading docs...', 'Fixing a bug...', 'Adding feature...',
]

type DevMoveState = 'idle' | 'walking_to_tree' | 'working' | 'walking_home'

interface DevActivityState {
  userId: string
  displayName: string
  label: AgentLabel
  labelEntity: pc.Entity
  originalPosition: pc.Vec3
  originalYaw: number
  wasSitting: boolean
  currentRepoName: string | null
  targetX: number
  targetZ: number
  moveState: DevMoveState
  idleTimer: number
  phraseTimer: number
}

export class CharacterSystem {
  private factory: CharacterFactory
  private kayKitFactory: KayKitCharacterFactory
  private characters: CharacterEntity[] = []
  private app: Application | null = null

  // Dev activity state
  private activeDevs = new Map<string, DevActivityState>()
  private getTreePos: TreePositionLookup = () => null

  // Takeover mode — blocks NPC AI for the taken-over character
  private takeoverUserId: string | null = null

  constructor(loader: AssetLoader) {
    this.factory = new CharacterFactory(loader)
    this.kayKitFactory = new KayKitCharacterFactory(loader)
  }

  /**
   * Build characters for all members and add them to the scene.
   *
   * @param app - PlayCanvas application wrapper
   * @param members - Team members to create characters for
   * @param memberHouseMap - Maps member user_id → house data (bed position, seats)
   * @param allSeats - All registered seats from all buildings
   */
  async build(
    app: Application,
    members: EngineMember[],
    memberHouseMap: Map<string, HouseResult>,
    allSeats: InteractionPoint[],
  ): Promise<void> {
    this.app = app

    // Track which seats are taken so we don't double-assign
    const takenSeats = new Set<string>()

    for (const member of members) {
      const house = memberHouseMap.get(member.user_id)
      const placement = this.getPlacement(member, house, allSeats, takenSeats)

      // Dispatch: KayKit characters vs legacy Kenney Blocky
      const config = parseCharacterModel(member.character_model)
      let character: CharacterEntity

      if (isKayKitConfig(config)) {
        character = await this.kayKitFactory.create(
          member.user_id,
          member.name,
          config,
          placement.x,
          placement.y,
          placement.z,
          placement.yaw,
          placement.sitting,
        )
      } else {
        const variant = CharacterFactory.getVariant(
          member.user_id,
          member.character_model,
        )
        character = await this.factory.create(
          member.user_id,
          member.name,
          variant,
          placement.x,
          placement.y,
          placement.z,
          placement.yaw,
          placement.sitting,
        )
      }

      // Add to scene — animation starts on first tick (activate=true set in factory)
      app.root.addChild(character.entity)
      this.characters.push(character)

      // Register name label for billboard facing
      const label = character.entity.findByTag('billboard')[0] as pc.Entity | undefined
      if (label) app.registerBillboard(label)

      // Add level badge above name label (if XP data available)
      if (member.level && member.level > 1) {
        const badgeHeight = isKayKitConfig(config) ? 1.2 : 1.5
        const badge = createLevelBadge(
          member.level,
          member.level_name || 'seedling',
          app.app.graphicsDevice,
          badgeHeight,
        )
        character.entity.addChild(badge)
        app.registerBillboard(badge)
      }
    }
  }

  /** Wire in tree position lookup for dev activity movement. */
  setTreePositionLookup(fn: TreePositionLookup): void {
    this.getTreePos = fn
  }

  /** Set/clear which user is in takeover mode (blocks NPC AI for that character). */
  setTakeoverUser(userId: string | null): void {
    this.takeoverUserId = userId
    // If entering takeover, clean up any active dev activity state for this user
    if (userId) {
      const state = this.activeDevs.get(userId)
      if (state) this.cleanupActivityState(userId, state)
    }
  }

  // ─── Dev Activity ──────────────────────────────

  /** Handle a live dev activity event — move character to tree and show label. */
  handleDevActivity(activity: EngineDevActivity): void {
    if (!this.app) {
      console.debug('[CharacterSystem] handleDevActivity: no app')
      return
    }

    // Resolve character: try user_id first, then fallback to actor_name
    let character: CharacterEntity | undefined
    if (activity.user_id) {
      character = this.getCharacter(activity.user_id)
    }
    if (!character && activity.actor_name) {
      character = this.getCharacterByName(activity.actor_name)
      console.debug('[CharacterSystem] user_id lookup failed, name fallback:',
        activity.actor_name, character ? 'found' : 'not found')
    }
    if (!character) {
      console.debug('[CharacterSystem] No character found for dev activity',
        { user_id: activity.user_id, actor_name: activity.actor_name })
      return
    }

    // Use the character's memberId as the canonical key (handles name-fallback case)
    const resolvedId = character.memberId

    // Skip movement for character under player takeover control
    if (resolvedId === this.takeoverUserId) {
      console.debug('[CharacterSystem] Skipping dev activity — character in takeover mode')
      return
    }

    // Session ended or completed → return to seat
    if (
      activity.event_type === 'session_end' ||
      activity.status === 'completed' ||
      activity.status === 'failed'
    ) {
      console.debug('[CharacterSystem] Session end/completed → return to seat', resolvedId)
      this.returnToSeat(resolvedId)
      return
    }

    // Get or create activity state
    let state = this.activeDevs.get(resolvedId)
    if (!state) {
      const newState = this.createActivityState(character, activity, resolvedId)
      if (!newState) {
        console.debug('[CharacterSystem] Failed to create activity state')
        return
      }
      state = newState
      this.activeDevs.set(resolvedId, state)
    }

    // Update label text
    const displayName = activity.actor_name || character.memberName
    state.displayName = displayName
    state.label.setText(displayName, this.formatMessage(activity))
    state.idleTimer = 0

    // If repo changed (or first event with a repo), walk to the tree
    if (activity.repo_name && activity.repo_name !== state.currentRepoName) {
      const treePos = this.getTreePos(activity.repo_name)
      if (treePos) {
        console.debug('[CharacterSystem] Walking to tree:', activity.repo_name,
          'at', treePos.x.toFixed(1), treePos.z.toFixed(1))
        state.currentRepoName = activity.repo_name
        state.targetX = treePos.x + DEV_TREE_OFFSET_X
        state.targetZ = treePos.z + DEV_TREE_OFFSET_Z
        state.moveState = 'walking_to_tree'
        this.startWalkAnim(character)
      } else {
        console.debug('[CharacterSystem] Tree not found for repo:', activity.repo_name, '→ orchard fallback')
        this.walkToOrchardFallback(character, state)
      }
    } else if (!activity.repo_name && state.moveState === 'idle') {
      // No repo_name at all — walk to orchard area so movement is visible
      console.debug('[CharacterSystem] No repo_name → orchard fallback')
      this.walkToOrchardFallback(character, state)
    }
  }

  /** Per-frame update — tick walking and idle timers for active devs. */
  update(dt: number): void {
    for (const [userId, state] of this.activeDevs) {
      if (userId === this.takeoverUserId) continue // skip player-controlled character
      const character = this.getCharacter(userId)
      if (!character) continue

      switch (state.moveState) {
        case 'walking_to_tree':
          this.tickWalking(character, state, dt, 'working')
          break

        case 'working': {
          state.idleTimer += dt
          state.phraseTimer += dt

          // Cycle label phrases to show the character is "alive" and engaged
          if (state.phraseTimer >= DEV_PHRASE_INTERVAL) {
            state.phraseTimer = 0
            const phrase = DEV_WORKING_PHRASES[
              Math.floor(Math.random() * DEV_WORKING_PHRASES.length)
            ]
            state.label.setText(state.displayName, phrase)
          }

          // Gentle look-around: oscillate yaw so the character appears engaged
          const lookAngle = Math.sin(state.idleTimer * 0.5) * 15
          const baseYaw = Math.atan2(
            state.targetX - state.originalPosition.x,
            state.targetZ - state.originalPosition.z,
          ) * (180 / Math.PI)
          character.entity.setEulerAngles(0, baseYaw + lookAngle, 0)

          if (state.idleTimer >= DEV_IDLE_TIMEOUT) {
            this.returnToSeat(userId)
          }
          break
        }

        case 'walking_home': {
          const arrived = this.tickWalking(character, state, dt, 'idle')
          if (arrived) {
            // Restore sitting if they were seated
            if (state.wasSitting) {
              character.entity.anim?.setBoolean('sitting', true)
            }
            // Clean up activity state
            this.cleanupActivityState(userId, state)
          }
          break
        }
      }
    }
  }

  /** Trigger return-to-seat for a developer. */
  private returnToSeat(userId: string): void {
    const state = this.activeDevs.get(userId)
    if (!state) return

    const character = this.getCharacter(userId)
    if (!character) {
      this.cleanupActivityState(userId, state)
      return
    }

    state.targetX = state.originalPosition.x
    state.targetZ = state.originalPosition.z
    state.moveState = 'walking_home'
    state.currentRepoName = null
    this.startWalkAnim(character)
  }

  /** Create DevActivityState for a newly active developer. */
  private createActivityState(
    character: CharacterEntity,
    activity: EngineDevActivity,
    resolvedId: string,
  ): DevActivityState | null {
    if (!this.app) return null

    const pos = character.entity.getPosition()
    const euler = character.entity.getEulerAngles()
    const wasSitting = character.entity.anim?.getBoolean('sitting') ?? false
    const displayName = activity.actor_name || character.memberName

    // Create activity label (green tint to distinguish from blue agent labels)
    const label = new AgentLabel(this.app.app.graphicsDevice)
    const labelEntity = label.create(displayName, this.formatMessage(activity))
    label.setColor(0.12, 0.47, 0.24)
    label.setHeight(DEV_LABEL_HEIGHT)
    character.entity.addChild(labelEntity)
    this.app.registerBillboard(labelEntity)

    return {
      userId: resolvedId,
      displayName,
      label,
      labelEntity,
      originalPosition: new pc.Vec3(pos.x, pos.y, pos.z),
      originalYaw: euler.y,
      wasSitting,
      currentRepoName: null,
      targetX: pos.x,
      targetZ: pos.z,
      moveState: 'idle',
      idleTimer: 0,
      phraseTimer: 0,
    }
  }

  /** Tick walking toward target. Returns true if arrived. */
  private tickWalking(
    character: CharacterEntity,
    state: DevActivityState,
    dt: number,
    arrivalState: DevMoveState,
  ): boolean {
    const pos = character.entity.getPosition()
    const dx = state.targetX - pos.x
    const dz = state.targetZ - pos.z
    const distSq = dx * dx + dz * dz

    if (distSq < DEV_ARRIVE_DIST_SQ) {
      // Arrived
      state.moveState = arrivalState
      character.entity.anim?.setInteger('speed', 0)
      return true
    }

    const dist = Math.sqrt(distSq)
    const step = DEV_WALK_SPEED * dt
    const nx = dx / dist
    const nz = dz / dist

    character.entity.setPosition(
      pos.x + nx * step,
      0,
      pos.z + nz * step,
    )

    // Face walking direction
    const yaw = Math.atan2(nx, nz) * (180 / Math.PI)
    character.entity.setEulerAngles(0, yaw, 0)

    return false
  }

  /** Format the activity message for the label bottom line. */
  private formatMessage(activity: EngineDevActivity): string {
    const msg = activity.message
    switch (activity.event_type) {
      case 'commit':
        return msg ? (msg.length > 40 ? msg.slice(0, 37) + '...' : msg) : 'Committing...'
      case 'file_change':
        if (activity.file_path) {
          const parts = activity.file_path.split('/')
          return `Editing ${parts[parts.length - 1]}`
        }
        return msg || 'Editing files...'
      case 'session_start':
        return 'Starting session...'
      case 'session_end':
        return 'Session ended'
      case 'tool_call':
        return msg || 'Running tool...'
      case 'tool_error':
      case 'api_error':
        return msg || 'Error encountered'
      default:
        return msg || 'Working...'
    }
  }

  /** Clean up activity state and label for a developer. */
  private cleanupActivityState(userId: string, state: DevActivityState): void {
    if (this.app) {
      this.app.unregisterBillboard(state.labelEntity)
    }
    state.label.destroy()
    this.activeDevs.delete(userId)
  }

  // ─── Dev Activity Helpers ───────────────────────

  /** Find a character by display name (case-insensitive fallback for missing user_id). */
  private getCharacterByName(name: string): CharacterEntity | undefined {
    const lower = name.toLowerCase()
    return this.characters.find(c => c.memberName.toLowerCase() === lower)
  }

  /** Start walk animation on a character (stand up + walk). */
  private startWalkAnim(character: CharacterEntity): void {
    const anim = character.entity.anim
    if (anim) {
      anim.setBoolean('sitting', false)
      anim.setInteger('speed', 1)
    }
  }

  /** Walk the character to the orchard fallback position (when no repo tree is available). */
  private walkToOrchardFallback(character: CharacterEntity, state: DevActivityState): void {
    state.currentRepoName = null
    // Add small random jitter so multiple devs don't stack on the same spot
    state.targetX = DEV_ORCHARD_FALLBACK_X + (Math.random() - 0.5) * 3
    state.targetZ = DEV_ORCHARD_FALLBACK_Z + (Math.random() - 0.5) * 3
    state.moveState = 'walking_to_tree'
    this.startWalkAnim(character)
  }

  // ─── Placement & Query ──────────────────────────

  /** Determine where to place a character based on presence. */
  private getPlacement(
    member: EngineMember,
    house: HouseResult | undefined,
    allSeats: InteractionPoint[],
    takenSeats: Set<string>,
  ): { x: number; y: number; z: number; yaw: number; sitting: boolean } {
    const presence = member.presence ?? 'active'

    // 'at_home' → stand at house bed position
    if (presence === 'at_home' && house) {
      return {
        x: house.bedPosition.x,
        y: 0,
        z: house.bedPosition.z,
        yaw: 0,
        sitting: false,
      }
    }

    // 'active' → try to seat at their house desk first
    if (presence === 'active' && house) {
      const deskSeat = house.seats.find(s => !takenSeats.has(s.id))
      if (deskSeat) {
        takenSeats.add(deskSeat.id)
        return {
          x: deskSeat.x,
          y: deskSeat.y,
          z: deskSeat.z,
          yaw: deskSeat.yaw,
          sitting: true,
        }
      }
    }

    // 'on_break' → try pool or coffee bar seats
    if (presence === 'on_break') {
      const breakZones = ['pool_resort', 'coffee_bar']
      for (const zone of breakZones) {
        const seat = allSeats.find(s => s.zone === zone && !takenSeats.has(s.id))
        if (seat) {
          takenSeats.add(seat.id)
          return {
            x: seat.x,
            y: seat.y,
            z: seat.z,
            yaw: seat.yaw,
            sitting: true,
          }
        }
      }
    }

    // Fallback: any available seat
    const anySeat = allSeats.find(s => !takenSeats.has(s.id))
    if (anySeat) {
      takenSeats.add(anySeat.id)
      return {
        x: anySeat.x,
        y: anySeat.y,
        z: anySeat.z,
        yaw: anySeat.yaw,
        sitting: true,
      }
    }

    // Last resort: stand at house or origin
    if (house) {
      return {
        x: house.bedPosition.x,
        y: 0,
        z: house.bedPosition.z,
        yaw: 0,
        sitting: false,
      }
    }

    return { x: 0, y: 0, z: 0, yaw: 0, sitting: false }
  }

  /** Get all character entities (for Phase 5 interaction picking). */
  getCharacters(): CharacterEntity[] {
    return this.characters
  }

  /** Find a character by member ID. */
  getCharacter(memberId: string): CharacterEntity | undefined {
    return this.characters.find(c => c.memberId === memberId)
  }

  destroy(): void {
    // Clean up active dev activity states (labels + GPU resources)
    for (const [userId, state] of this.activeDevs) {
      this.cleanupActivityState(userId, state)
    }

    for (const char of this.characters) {
      if (this.app) {
        const label = char.entity.findByTag('billboard')[0] as pc.Entity | undefined
        if (label) this.app.unregisterBillboard(label)
      }
      // Dispose label material + texture before destroying entity (GPU resource cleanup)
      const labelEntity = char.entity.findByName('NameLabel') as pc.Entity | null
      if (labelEntity?.render?.meshInstances[0]) {
        disposeMaterial(labelEntity.render.meshInstances[0].material)
      }
      // Dispose KayKit cloned tinting materials (type-safe WeakMap lookup)
      const clonedMats = getClonedMaterials(char.entity)
      if (clonedMats) {
        for (const mat of clonedMats) disposeMaterial(mat)
      }
      char.entity.destroy()
    }
    this.characters = []
    this.activeDevs.clear()
    this.app = null
    this.factory.clear()
    this.kayKitFactory.clear()
  }
}
