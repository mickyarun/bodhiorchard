/**
 * CharacterSystem — renders character entities from authoritative OrgRoom state.
 *
 * Every character in the garden corresponds to a `MemberState` on the Colyseus
 * server. This system is a pure renderer: it spawns, updates, and removes
 * entities in response to snapshot callbacks from `OrgRoomClient`. The server
 * owns position, presence placement, and dev-activity walking.
 *
 * Legacy local simulation (presence-based placement, dev activity walking,
 * return-to-seat timers) lived here before the multiplayer port and has been
 * removed — see `multiplayer/src/sim/DevActivitySim.ts` for the server version.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { AssetLoader } from '../assets/AssetLoader'
import { CharacterFactory, type CharacterEntity } from './CharacterFactory'
import { KayKitCharacterFactory, getClonedMaterials } from './KayKitCharacterFactory'
import { parseCharacterModel, isKayKitConfig } from './CharacterConfig'
import { createLevelBadge } from './LevelBadge'
import { disposeMaterial } from '../utils/EntityUtils'

/** Minimum snapshot shape needed to spawn/update a server-driven character. */
export interface CharacterSnapshot {
  userId: string
  name: string
  characterModel: string
  level: number
  levelName: string
  x: number
  y: number
  z: number
  yaw: number
  animState: string  // idle | walk | sit | sleep | sprint | jump
  labelName: string
  labelMessage: string
}

export class CharacterSystem {
  private factory: CharacterFactory
  private kayKitFactory: KayKitCharacterFactory
  private characters: CharacterEntity[] = []
  private app: Application | null = null

  // Parent entity for all character entities. Created in build() so it gets
  // swept into GardenRoot by wrapGardenRoot() — this ensures characters are
  // hidden when interior mode sets gardenRoot.enabled = false.
  private characterRoot: pc.Entity | null = null

  // Takeover mode — the userId whose character is under local WASD control.
  // Used to skip snapshot updates for that character (client-side prediction).
  private takeoverUserId: string | null = null

  // Track pending spawns to prevent duplicate async spawn races
  private spawning = new Set<string>()

  /** Optional callback to check if a user is mounted (set by GardenEngine). */
  isUserMounted: ((userId: string) => boolean) | null = null

  constructor(loader: AssetLoader) {
    this.factory = new CharacterFactory(loader)
    this.kayKitFactory = new KayKitCharacterFactory(loader)
  }

  /** Set the PlayCanvas Application (required for server-driven spawns). */
  setApp(app: Application): void {
    this.app = app
  }

  /**
   * Prepare the system for rendering. Creates a CharacterRoot parent entity
   * (swept into GardenRoot by SceneManager.wrapGardenRoot) and stores the
   * app handle. Actual character entities are spawned via `spawnFromSnapshot`
   * when OrgRoom state events arrive.
   */
  build(app: Application): void {
    this.app = app
    this.characterRoot = new pc.Entity('CharacterRoot')
    app.root.addChild(this.characterRoot)
  }

  // ─── Server-Driven Rendering ───────────────────

  /**
   * Spawn a character from a server snapshot. Creates the character entity
   * using the existing factory infrastructure, then positions it per server state.
   *
   * Idempotent — returns existing character if already spawned.
   * Async — safe to call from server state listener callbacks; spawn races are deduped.
   */
  async spawnFromSnapshot(snapshot: CharacterSnapshot): Promise<void> {
    if (!this.app) return
    // Already spawned?
    if (this.characters.find(c => c.memberId === snapshot.userId)) return
    // Already spawning?
    if (this.spawning.has(snapshot.userId)) return
    this.spawning.add(snapshot.userId)

    try {
      const sitting = snapshot.animState === 'sit' || snapshot.animState === 'sleep'
      const config = parseCharacterModel(snapshot.characterModel)
      let character: CharacterEntity

      if (isKayKitConfig(config)) {
        character = await this.kayKitFactory.create(
          snapshot.userId,
          snapshot.name,
          config,
          snapshot.x,
          snapshot.y,
          snapshot.z,
          snapshot.yaw,
          sitting,
        )
      } else {
        const variant = CharacterFactory.getVariant(snapshot.userId, snapshot.characterModel)
        character = await this.factory.create(
          snapshot.userId,
          snapshot.name,
          variant,
          snapshot.x,
          snapshot.y,
          snapshot.z,
          snapshot.yaw,
          sitting,
        )
      }

      // Guard: the system may have been destroyed while we were awaiting
      if (!this.app) {
        character.entity.destroy()
        return
      }

      (this.characterRoot ?? this.app.root).addChild(character.entity)
      this.characters.push(character)

      // Register name label for billboard facing
      const label = character.entity.findByTag('billboard')[0] as pc.Entity | undefined
      if (label) this.app.registerBillboard(label)

      // Level badge
      if (snapshot.level > 1) {
        const badgeHeight = isKayKitConfig(config) ? 1.2 : 1.5
        const badge = createLevelBadge(
          snapshot.level,
          snapshot.levelName || 'seedling',
          this.app.app.graphicsDevice,
          badgeHeight,
        )
        character.entity.addChild(badge)
        this.app.registerBillboard(badge)
      }
    } finally {
      this.spawning.delete(snapshot.userId)
    }
  }

  /**
   * Update a character's position + animation from a server snapshot.
   * Called on every server state change for this member.
   */
  updateFromSnapshot(snapshot: CharacterSnapshot): void {
    const character = this.getCharacter(snapshot.userId)
    if (!character) {
      void this.spawnFromSnapshot(snapshot)
      return
    }

    if (snapshot.userId === this.takeoverUserId) return

    // Skip position + animation updates for characters mounted on a vehicle.
    // Their position is driven by VehicleSystem (parented to the horse entity).
    if (this.isUserMounted?.(snapshot.userId)) return

    character.entity.setPosition(snapshot.x, snapshot.y, snapshot.z)
    character.entity.setEulerAngles(0, snapshot.yaw, 0)

    const anim = character.entity.anim
    if (anim) {
      const isSitting = snapshot.animState === 'sit' || snapshot.animState === 'sleep'
      anim.setBoolean('sitting', isSitting)
      const speed = snapshot.animState === 'walk' || snapshot.animState === 'sprint' ? 1 : 0
      anim.setInteger('speed', speed)
      // Tree-activity working animations: interact=1, use-item=2, else=0
      const working = snapshot.animState === 'interact' ? 1
        : snapshot.animState === 'use-item' ? 2
        : 0
      anim.setInteger('working', working)
    }
  }

  /** Remove a character by userId (when server MemberState is removed). */
  removeByUserId(userId: string): void {
    const idx = this.characters.findIndex(c => c.memberId === userId)
    if (idx === -1) return
    const character = this.characters[idx]
    if (this.app) {
      const label = character.entity.findByTag('billboard')[0] as pc.Entity | undefined
      if (label) this.app.unregisterBillboard(label)
    }
    character.entity.destroy()
    this.characters.splice(idx, 1)
  }

  /**
   * Mark which user is in local takeover mode. Snapshot updates for this
   * user are skipped (client-side prediction — the local WASD controller
   * drives the entity, and the server echoes positions back via takeoverSessionId).
   */
  setTakeoverUser(userId: string | null): void {
    this.takeoverUserId = userId
  }

  /** Get all character entities (used by interaction picking). */
  getCharacters(): CharacterEntity[] {
    return this.characters
  }

  /** Find a character by member ID. */
  getCharacter(memberId: string): CharacterEntity | undefined {
    return this.characters.find(c => c.memberId === memberId)
  }

  /** Get the pc.Entity for a member (used by VehicleSystem to parent vehicles). */
  getEntity(memberId: string): pc.Entity | undefined {
    return this.getCharacter(memberId)?.entity
  }

  destroy(): void {
    // Destroy the parent first — all children are destroyed recursively.
    // But we still iterate to unregister billboards and dispose GPU resources.
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
    this.characterRoot?.destroy()
    this.characterRoot = null
    this.app = null
    this.factory.clear()
    this.kayKitFactory.clear()
  }
}
