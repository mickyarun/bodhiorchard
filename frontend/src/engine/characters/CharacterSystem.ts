// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
import type { CharacterEntity } from './CharacterTypes'
import { KayKitCharacterFactory, getClonedMaterials } from './KayKitCharacterFactory'
import { parseCharacterModel } from './CharacterConfig'
import { createLevelBadge } from './LevelBadge'
import { disposeMaterial } from '../utils/EntityUtils'
import { lerpPose, POSITION_LERP, type PoseState } from '../multiplayer/RemoteInterp'

/**
 * Per-character pose target. Extends the shared PoseState with a `seated`
 * flag so the per-frame update loop knows to snap (chair) vs lerp (walk).
 *
 * The target is written by server snapshots (~20Hz); update(dt) reads it
 * every render frame (60Hz) and re-applies position and rotation.
 *
 * Why per-frame apply and not per-snapshot: the anim component, while a
 * walk/sprint state is active, re-evaluates its bindings during PlayCanvas's
 * internal update phase and can overwrite the wrapper's transform between
 * snapshots. Re-applying every frame mirrors the NetworkedPlayer pattern
 * used by cafeteria / coffeebar remote players.
 */
interface RenderTarget extends PoseState {
  /** Seated avatars snap (no position lerp) so they don't drift off the chair. */
  seated: boolean
}

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
  /** Server-authoritative location hint. Interior contexts hide the entity. */
  locationContext?: string
}

/**
 * locationContext values that should hide the avatar (user is inside a
 * shared interior). MUST stay in sync with the backend set at
 * `multiplayer/src/rooms/OrgRoom.ts` (INTERIOR_LOCATIONS). When adding
 * a new interior, update both files — the server's entry drives the
 * `skip walkHome + stamp locationContext` behaviour on takeover_end, and
 * the client's entry drives the visibility check in updateFromSnapshot.
 */
const INTERIOR_LOCATIONS = new Set(['cafeteria', 'coffeebar'])

function isInteriorLocation(ctx: string | undefined): boolean {
  return !!ctx && INTERIOR_LOCATIONS.has(ctx)
}

export class CharacterSystem {
  private kayKitFactory: KayKitCharacterFactory
  private characters: CharacterEntity[] = []
  private app: Application | null = null

  // Parent entity for all character entities. Created in build() so it gets
  // swept into GardenRoot by wrapGardenRoot() — this ensures characters are
  // hidden when interior mode sets gardenRoot.enabled = false.
  private characterRoot: pc.Entity | null = null

  /** Bound postUpdate handler so we can unregister it in destroy(). */
  private readonly _postUpdateHandler = (_dt: number): void => this.update(_dt)

  /** Exposed so interior modes (cafeteria, coffee bar) can hide org-member
   *  avatars explicitly. Usually redundant — characterRoot is reparented
   *  into gardenRoot — but acts as a safety net. */
  get root(): pc.Entity | null { return this.characterRoot }

  // Takeover mode — the userId whose character is under local WASD control.
  // Used to skip snapshot updates for that character (client-side prediction).
  private takeoverUserId: string | null = null

  // Track pending spawns to prevent duplicate async spawn races
  private spawning = new Set<string>()

  /** Scratch quaternion reused across all characters within a single update() tick. */
  private readonly _yawQuat = new pc.Quat()

  /**
   * Latest server snapshot target per user. Written by updateFromSnapshot(),
   * consumed by update(dt). Characters excluded here have their transforms
   * driven elsewhere (local takeover, vehicle mounts, interior hidden) — see
   * `shouldSkipTransformApply` for the full rule set.
   */
  private readonly renderTargets = new Map<string, RenderTarget>()

  /** Optional callback to check if a user is mounted (set by GardenEngine). */
  isUserMounted: ((userId: string) => boolean) | null = null

  constructor(loader: AssetLoader) {
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
    // Register on POST-update. PlayCanvas's update order per frame is:
    //   1. app.fire('update')               ← our onUpdate runs here
    //   2. systems.fire('update')
    //   3. systems.fire('animationUpdate')  ← anim component evaluates bindings
    //   4. systems.fire('postUpdate')       ← we run here
    //   5. render
    // Applying on step 1 lets anim's step 3 overwrite our setLocalRotation,
    // causing remote characters to slide without visibly turning. postUpdate
    // is fired on `systems`, not the app itself — listening on `app.on` would
    // silently never fire.
    app.app.systems.on('postUpdate', this._postUpdateHandler)
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
      const character: CharacterEntity = await this.kayKitFactory.create(
        snapshot.userId,
        snapshot.name,
        config,
        snapshot.x,
        snapshot.y,
        snapshot.z,
        snapshot.yaw,
        sitting,
      )

      // Guard: the system may have been destroyed while we were awaiting
      if (!this.app) {
        character.entity.destroy()
        return
      }

      (this.characterRoot ?? this.app.root).addChild(character.entity)
      // If the member was already inside an interior when we first saw them,
      // render the entity hidden — updateFromSnapshot re-enables it when
      // locationContext returns to the garden.
      if (isInteriorLocation(snapshot.locationContext)) {
        character.entity.enabled = false
      }
      this.characters.push(character)

      // Register name label for billboard facing
      const label = character.entity.findByTag('billboard')[0] as pc.Entity | undefined
      if (label) this.app.registerBillboard(label)

      // Level badge — KayKit characters are short (~0.7 m), so the badge
      // sits closer to the head than the old Kenney-blocky offset.
      if (snapshot.level > 1) {
        const badge = createLevelBadge(
          snapshot.level,
          snapshot.levelName || 'seedling',
          this.app.app.graphicsDevice,
          1.2,
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

    // Hide the avatar while the user is inside a shared interior. The server
    // stops simulating movement and stamps locationContext="cafeteria" (or
    // "coffeebar") — every observer hides the entity for the duration so
    // nobody sees it frozen at the door. On takeover_start the server resets
    // locationContext to "garden" and the entity re-enables here.
    const shouldHide = isInteriorLocation(snapshot.locationContext)
    if (character.entity.enabled === shouldHide) {
      character.entity.enabled = !shouldHide
    }
    // Skip position updates while hidden — saves work and avoids visible
    // teleport when the server re-places the member on exit.
    if (shouldHide) return

    // Skip position + animation updates for characters mounted on a vehicle.
    // Their position is driven by VehicleSystem (parented to the horse entity).
    if (this.isUserMounted?.(snapshot.userId)) return

    // Record the target. The per-frame update(dt) loop applies it every render
    // frame so the anim component can't clobber the transform between snapshots.
    const seated = snapshot.animState === 'sit' || snapshot.animState === 'sleep'
    const existing = this.renderTargets.get(snapshot.userId)
    if (existing) {
      // Mutate in place — avoids allocating a new target on every 20Hz snapshot.
      existing.targetX = snapshot.x
      existing.targetY = snapshot.y
      existing.targetZ = snapshot.z
      existing.targetYaw = snapshot.yaw
      existing.seated = seated
    } else {
      // First snapshot for this character: seed current* from the entity's
      // spawn pose so update(dt)'s lerp doesn't fly in from (0,0,0).
      const pos = character.entity.getPosition()
      this.renderTargets.set(snapshot.userId, {
        targetX: snapshot.x,
        targetY: snapshot.y,
        targetZ: snapshot.z,
        targetYaw: snapshot.yaw,
        currentX: pos.x,
        currentY: pos.y,
        currentZ: pos.z,
        currentYaw: snapshot.yaw,
        seated,
      })
    }

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
      // Emotes: wave=1, cheer=2
      const emote = snapshot.animState === 'wave' ? 1
        : snapshot.animState === 'cheer' ? 2
        : 0
      anim.setInteger('emote', emote)
    }
  }

  /**
   * Per-frame transform apply. Called from SceneManager.update(dt). Mirrors
   * NetworkedPlayer.update() in intent: re-apply position and rotation on
   * every render frame so the anim component's internal binding can't
   * overwrite them between 20Hz server snapshots.
   *
   * Rotation is applied directly (no lerp) — drives straight to target yaw
   * via quaternion. Position is lerped toward target for smooth motion.
   */
  update(_dt: number): void {
    for (const [userId, target] of this.renderTargets) {
      if (userId === this.takeoverUserId) continue
      const character = this.getCharacter(userId)
      if (!character || !character.entity.enabled) continue
      if (this.isUserMounted?.(userId)) continue

      const entity = character.entity
      if (target.seated) {
        // Snap to target — prevents visible drift off the chair.
        target.currentX = target.targetX
        target.currentY = target.targetY
        target.currentZ = target.targetZ
        target.currentYaw = target.targetYaw
      } else {
        // Shared lerp: position + shortest-path yaw. Lerps from our OWN
        // tracked current*, never reads back from the entity — the anim
        // component can clobber entity transforms between postUpdate runs,
        // and reading clobbered values would destabilise the lerp.
        lerpPose(target, POSITION_LERP)
      }
      entity.setPosition(target.currentX, target.currentY, target.currentZ)
      // Rotation via quaternion — bypasses the Euler decomposition round-trip
      // that setEulerAngles internally does, whose output can surface a
      // gimbal-flipped (180, y', 180) form for some yaw values.
      this._yawQuat.setFromEulerAngles(0, target.currentYaw, 0)
      entity.setLocalRotation(this._yawQuat)
    }
  }

  /** Remove a character by userId (when server MemberState is removed). */
  removeByUserId(userId: string): void {
    this.renderTargets.delete(userId)
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
    // The locally-controlled avatar owns its own transform — drop the server
    // target so update(dt) doesn't fight the WASD controller.
    if (userId) this.renderTargets.delete(userId)
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
    // Unregister the postUpdate handler before app teardown.
    this.app?.app.systems.off('postUpdate', this._postUpdateHandler)
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
    this.renderTargets.clear()
    this.characterRoot?.destroy()
    this.characterRoot = null
    this.app = null
    this.kayKitFactory.clear()
  }
}
