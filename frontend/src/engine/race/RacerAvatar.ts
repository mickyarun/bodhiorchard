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
 * RacerAvatar — one racer's avatar in the race scene.
 *
 * Reuses the shared KayKitCharacterFactory so we never re-implement glTF
 * loading or tinting. The KayKit locomotion state graph's Walk state
 * defaults to the Walking_A track; we swap its track to Running_A at
 * runtime when the racer is sprinting, so sprint reads as a proper run
 * while a casual move reads as a walk.
 *
 * Track lookup goes through findAnimTrack against the container's loaded
 * animations — no hard-coded string outside the animation manifest.
 *
 * Animation driving matches the dashboard's `CharacterSystem` pattern:
 * setPosition each frame + setInteger('speed', 0|1) to switch Idle ↔ Walk.
 * Never touches anim.speed (varying the playback multiplier caused visible
 * "jumping" because the step cycle re-keyed mid-stride).
 *
 * Ownership:
 *   - Owns the wrapper entity returned by the factory → destroys it.
 *   - Owns the cloned tinting materials → nulls map refs + destroys.
 *   - Does NOT own the factory's cached animation GLBs (shared, lifecycle
 *     tied to the factory).
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import { KayKitCharacterFactory, getClonedMaterials } from '../characters/KayKitCharacterFactory'
import { findAnimTrack, type ContainerWithAnims } from '../characters/AnimUtils'
import { getAnimationGLB } from '../characters/KayKitManifest'
import type { CharacterConfig } from '../characters/CharacterConfig'
import { disposeEntity, safeDestroyMaterial } from './dispose'

/**
 * Visual config for one racer — replaces the deleted RacerPresets module.
 * Values come from each member's profile in step 2 / step 6 of race v2.
 */
export interface RacerPreset {
  name: string
  config: CharacterConfig
}

/** Animation track names used by the race scene — all resolved via findAnimTrack. */
const WALK_TRACK_NAME = 'Walking_A'
const RUN_TRACK_NAME = 'Running_A'

/**
 * Scale multiplier applied on top of KayKit's built-in KAYKIT_TARGET_HEIGHT.
 * Base KayKit chars are tuned to 0.7m tall (indoor furniture scale); the
 * racing environment reads better at ~0.9m tall (the 1.3x bump).
 */
const RACE_AVATAR_SCALE = 1.3

/** Fixed AABB for the skinned mesh — avoids per-frame bounding-box recalc. */
const AABB_CENTER = new pc.Vec3(0, 0.45, 0)
const AABB_HALF_EXTENTS = new pc.Vec3(0.3, 0.5, 0.3)

/** KayKit characters default-face -Z; rotate 90° so they face +X (track direction). */
const AVATAR_YAW_DEG = 90

/** Below this velocity, swap back to the Idle state. Avoids swap-thrash at rest. */
const IDLE_SWAP_THRESHOLD_MPS = 0.5

/** Above this velocity, assume the player is sprinting (swap Walk → Running_A). */
const SPRINT_SWAP_THRESHOLD_MPS = 4.0

export class RacerAvatar {
  readonly racerId: string
  readonly laneZ: number

  private factory: AssetFactoryBundle
  private preset: RacerPreset
  private wrapper: pc.Entity | null = null
  private walkTrack: pc.AnimTrack | null = null
  private runTrack: pc.AnimTrack | null = null
  private currentAnimState: 'idle' | 'walk' | 'run' = 'idle'

  /**
   * Server updates land at 20 Hz. To avoid visibly jerky motion we lerp
   * toward the server-supplied target each render frame. `targetX` is
   * set by `setKinematics`; `displayX` is what we actually write to the
   * entity transform.
   */
  private targetX = 0
  private displayX = 0
  private lastServerVelocity = 0
  private initialized = false

  /**
   * When the server marks this racer as finished, we force the anim graph
   * through Idle → Cheer (emote=2) regardless of incoming kinematics. The
   * flag also makes setKinematics a no-op for anim-state picking so a
   * late-arriving velocity patch doesn't yank the avatar back into Walk
   * between the finish-line crossing and the UI phase change.
   */
  private finished = false

  /** Display name pulled from the preset — consumed by the HUD. */
  get displayName(): string {
    return this.preset.name
  }

  constructor(racerId: string, preset: RacerPreset, laneZ: number, factory: AssetFactoryBundle) {
    this.racerId = racerId
    this.preset = preset
    this.laneZ = laneZ
    this.factory = factory
  }

  async build(parent: pc.Entity): Promise<void> {
    const wrapper = await this.factory.characters.create(
      this.racerId,
      this.preset.name,
      this.preset.config,
      0, 0, this.laneZ,
      AVATAR_YAW_DEG,
      false, false,
    )
    parent.addChild(wrapper.entity)
    this.wrapper = wrapper.entity

    wrapper.entity.setLocalScale(RACE_AVATAR_SCALE, RACE_AVATAR_SCALE, RACE_AVATAR_SCALE)
    wrapper.entity.setLocalPosition(0, 0, this.laneZ)

    try {
      await this.loadLocomotionTracks()
      this.applyCustomAabb(wrapper.entity)
    } catch (err) {
      // If animation track loading fails we must tear down the partially
      // constructed wrapper + its cloned tint materials before rethrowing,
      // otherwise the caller has no handle to clean them up.
      this.destroy()
      throw err
    }
  }

  /**
   * Called whenever the server sends a new state patch (≈20 Hz). Stores
   * the target; the per-frame `update` lerps toward it so motion stays
   * smooth between server ticks.
   */
  setKinematics(x: number, velocityMps: number, isSprinting: boolean): void {
    if (!this.wrapper) return

    this.targetX = x
    this.lastServerVelocity = velocityMps
    if (!this.initialized) {
      // First patch: snap so the avatar isn't stuck at x=0 while lerping.
      this.displayX = x
      this.wrapper.setPosition(x, 0, this.laneZ)
      this.initialized = true
    }

    // After the finish line we hold the Cheer state — see `finished`.
    if (this.finished) return

    const nextState = this.pickAnimState(velocityMps, isSprinting)
    if (nextState === this.currentAnimState) return

    this.applyAnimState(nextState)
    this.currentAnimState = nextState
  }

  /**
   * Mark this racer as finished — switches the anim graph to the Cheer
   * state (emote=2) and latches out of the velocity-driven state machine.
   * Idempotent; calling with the current value is a no-op.
   */
  setFinished(finished: boolean): void {
    if (this.finished === finished) return
    this.finished = finished

    const anim = this.wrapper?.anim
    if (!anim) return

    if (finished) {
      // Push the graph through Walk → Idle (speed=0) so the Idle → Cheer
      // edge can fire on the next tick. Cheer has no direct transition
      // from Walk in LOCOMOTION_STATE_GRAPH.
      anim.setInteger('speed', 0)
      anim.setInteger('emote', 2)
      this.currentAnimState = 'idle'
    } else {
      anim.setInteger('emote', 0)
    }
  }

  /**
   * Per-render-frame smoothing. Extrapolates toward `targetX` using the
   * last known server velocity so the avatar keeps moving between
   * server patches instead of snapping each tick.
   */
  update(dtSec: number): void {
    if (!this.wrapper || !this.initialized) return

    // Extrapolate by the server's reported velocity; clamp to the target
    // so we don't overshoot past where the server last placed us.
    const predicted = this.displayX + this.lastServerVelocity * dtSec
    if (this.lastServerVelocity >= 0) {
      this.displayX = Math.min(predicted, this.targetX)
    } else {
      this.displayX = Math.max(predicted, this.targetX)
    }

    // Exponential catch-up: if we ever drift behind the server (e.g. after
    // a dropped packet) this lerp closes the gap within ~100 ms.
    const CATCHUP_PER_SEC = 10
    const alpha = 1 - Math.exp(-CATCHUP_PER_SEC * dtSec)
    this.displayX += (this.targetX - this.displayX) * alpha

    this.wrapper.setPosition(this.displayX, 0, this.laneZ)
  }

  /** Read-only access to the current display X — used by the camera. */
  getDisplayX(): number {
    return this.displayX
  }

  destroy(): void {
    if (!this.wrapper) return

    const clonedMats = getClonedMaterials(this.wrapper)
    if (clonedMats) for (const mat of clonedMats) safeDestroyMaterial(mat)

    disposeEntity(this.wrapper)
    this.wrapper = null
    this.walkTrack = null
    this.runTrack = null
    this.currentAnimState = 'idle'
    this.initialized = false
    this.finished = false
  }

  private pickAnimState(velocityMps: number, isSprinting: boolean): 'idle' | 'walk' | 'run' {
    if (velocityMps < IDLE_SWAP_THRESHOLD_MPS) return 'idle'
    if (isSprinting && velocityMps >= SPRINT_SWAP_THRESHOLD_MPS) return 'run'
    return 'walk'
  }

  private applyAnimState(state: 'idle' | 'walk' | 'run'): void {
    const anim = this.wrapper?.anim
    if (!anim) return
    const layer = anim.baseLayer
    if (!layer) return

    if (state === 'idle') {
      anim.setInteger('speed', 0)
      return
    }

    // Swap the Walk state's track to the appropriate variant.
    const track = state === 'run' ? this.runTrack : this.walkTrack
    if (track) layer.assignAnimation('Walk', track)
    anim.setInteger('speed', 1)
  }

  private async loadLocomotionTracks(): Promise<void> {
    const movementBasicPath = getAnimationGLB('movement_basic')
    const asset = await this.factory.loader.load(movementBasicPath)
    const container = asset.resource as ContainerWithAnims

    this.walkTrack = findAnimTrack(container, WALK_TRACK_NAME)
    this.runTrack = findAnimTrack(container, RUN_TRACK_NAME)
    if (!this.walkTrack) throw new Error(`RacerAvatar: missing ${WALK_TRACK_NAME} in ${movementBasicPath}`)
    if (!this.runTrack) throw new Error(`RacerAvatar: missing ${RUN_TRACK_NAME} in ${movementBasicPath}`)
  }

  private applyCustomAabb(wrapper: pc.Entity): void {
    const aabb = new pc.BoundingBox(AABB_CENTER.clone(), AABB_HALF_EXTENTS.clone())
    const renders = wrapper.findComponents('render') as pc.RenderComponent[]
    for (const rc of renders) rc.customAabb = aabb
  }
}

export interface AssetFactoryBundle {
  loader: AssetLoader
  characters: KayKitCharacterFactory
}
