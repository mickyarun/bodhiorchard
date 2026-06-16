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
 * loading or tinting. Owns the entity transform: the server's 1-D
 * `positionM` arc scalar is smoothed into `displayX` each frame, then a
 * TrackProjection maps (arc, lane offset) to world position + travel
 * heading — straight tracks reproduce the historical constant-lane-Z /
 * constant-yaw-90 behaviour exactly; circuits curve around the ring.
 *
 * The animation state machine (Idle/Walk/Run picking, knockdown,
 * finish-Cheer latch) lives in RacerAvatarAnim.
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
import type { CharacterConfig } from '../characters/CharacterConfig'
import { HURDLE_JUMP_WINDOW_MS } from '@shared/race/RaceConstants'
import type { RacerKinematics } from './types'
import { entityYawDeg, type TrackProjection } from './TrackProjection'
import { RacerAvatarAnim } from './RacerAvatarAnim'
import { disposeEntity, safeDestroyMaterial } from './dispose'

/**
 * Visual config for one racer — replaces the deleted RacerPresets module.
 * Values come from each member's profile in step 2 / step 6 of race v2.
 */
export interface RacerPreset {
  name: string
  config: CharacterConfig
}

/** Where this avatar runs: a lane offset projected onto the track shape. */
export interface RacerPlacement {
  /** Signed lateral offset of the lane centre from the track centreline. */
  laneOffsetM: number
  /** Shape-specific arc-length → world-pose mapping (straight or circuit). */
  projection: TrackProjection
}

/**
 * Scale multiplier applied on top of KayKit's built-in KAYKIT_TARGET_HEIGHT.
 * Base KayKit chars are tuned to 0.7m tall (indoor furniture scale); the
 * racing environment reads better at ~0.9m tall (the 1.3x bump).
 */
const RACE_AVATAR_SCALE = 1.3

/** Fixed AABB for the skinned mesh — avoids per-frame bounding-box recalc. */
const AABB_CENTER = new pc.Vec3(0, 0.45, 0)
const AABB_HALF_EXTENTS = new pc.Vec3(0.3, 0.5, 0.3)

/**
 * Yaw that points a KayKit model along travel heading 0 (+X). Verified
 * against pc.Quat: a +90° Y rotation maps local +Z → world +X, so this
 * is the yaw for a +Z-fronted model to face +X — the value the straight
 * track has always used.
 */
const AVATAR_YAW_DEG = 90

/**
 * Hurdle-jump hop arc scales with the racer's speed at takeoff: a
 * standing hop barely clears the bar while a boosted leap soars. Peak
 * height = MIN + PER_MPS · v, clamped to MAX.
 */
const JUMP_ARC_MIN_HEIGHT_M = 0.45
const JUMP_ARC_HEIGHT_PER_MPS = 0.06
const JUMP_ARC_MAX_HEIGHT_M = 1.05

/** Arc duration mirrors the server's airborne window so landing lines up. */
const JUMP_ARC_DURATION_S = HURDLE_JUMP_WINDOW_MS / 1000

export class RacerAvatar {
  readonly racerId: string

  private readonly laneOffsetM: number
  private readonly projection: TrackProjection
  private factory: AssetFactoryBundle
  private preset: RacerPreset
  private wrapper: pc.Entity | null = null
  private anim = new RacerAvatarAnim()

  /**
   * Server updates land at 20 Hz. To avoid visibly jerky motion we lerp
   * toward the server-supplied target each render frame. `targetX` is
   * the latest server arc length; `displayX` is the smoothed arc we
   * actually project onto the entity transform.
   */
  private targetX = 0
  private displayX = 0
  private lastServerVelocity = 0
  private initialized = false

  /**
   * Hurdle-jump hop: the server flags the racer airborne while its jump
   * window is open; we animate a sine arc on Y over the same duration so
   * the landing visually matches the physics window closing. Peak height
   * is captured at takeoff from the racer's current speed.
   */
  private airborne = false
  private jumpElapsedSec = 0
  private jumpPeakM = JUMP_ARC_MIN_HEIGHT_M

  /** Display name pulled from the preset — consumed by the HUD. */
  get displayName(): string {
    return this.preset.name
  }

  constructor(
    racerId: string,
    preset: RacerPreset,
    placement: RacerPlacement,
    factory: AssetFactoryBundle,
  ) {
    this.racerId = racerId
    this.preset = preset
    this.laneOffsetM = placement.laneOffsetM
    this.projection = placement.projection
    this.factory = factory
  }

  async build(parent: pc.Entity): Promise<void> {
    const start = this.projection.pose(0, this.laneOffsetM)
    const wrapper = await this.factory.characters.create(
      this.racerId,
      this.preset.name,
      this.preset.config,
      start.x, 0, start.z,
      this.modelYawFor(start.headingDeg),
      false, false,
    )
    parent.addChild(wrapper.entity)
    this.wrapper = wrapper.entity

    wrapper.entity.setLocalScale(RACE_AVATAR_SCALE, RACE_AVATAR_SCALE, RACE_AVATAR_SCALE)
    wrapper.entity.setLocalPosition(start.x, 0, start.z)

    try {
      this.anim.attach(wrapper.entity)
      await this.anim.load(this.factory.loader)
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
  setKinematics(k: RacerKinematics): void {
    if (!this.wrapper) return

    this.targetX = k.positionM
    this.lastServerVelocity = k.velocityMps
    if (k.isAirborne && !this.airborne) {
      this.jumpElapsedSec = 0
      this.jumpPeakM = Math.min(
        JUMP_ARC_MAX_HEIGHT_M,
        JUMP_ARC_MIN_HEIGHT_M + JUMP_ARC_HEIGHT_PER_MPS * k.velocityMps,
      )
    }
    this.airborne = k.isAirborne
    if (!this.initialized) {
      // First patch: snap so the avatar isn't stuck at arc 0 while lerping.
      this.displayX = k.positionM
      this.applyPose(0)
      this.initialized = true
    }

    this.anim.onKinematics(k.velocityMps, k.isSprinting, k.isKnockedDown)
  }

  /**
   * Mark this racer as finished — switches the anim graph to the Cheer
   * state and latches out of the velocity-driven state machine.
   * Idempotent; calling with the current value is a no-op.
   */
  setFinished(finished: boolean): void {
    this.anim.setFinished(finished)
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

    this.applyPose(this.jumpArcY(dtSec))
  }

  /**
   * Write the world transform for the current smoothed arc (`displayX`).
   * The projection turns arc + lane offset into position and travel
   * heading; on the straight track this reproduces the historical
   * behaviour exactly (constant lane Z, constant yaw 90).
   */
  private applyPose(jumpY: number): void {
    if (!this.wrapper) return
    const pose = this.projection.pose(this.displayX, this.laneOffsetM)
    this.wrapper.setPosition(pose.x, jumpY, pose.z)
    this.wrapper.setLocalEulerAngles(0, this.modelYawFor(pose.headingDeg), 0)
  }

  /**
   * Face the avatar along its direction of travel. Two pieces compose:
   * AVATAR_YAW_DEG (90) turns the +Z-fronted KayKit model onto heading 0
   * (+X), and entityYawDeg(-heading) rotates that frame onto the actual
   * travel tangent. Heading 0 therefore yields the straight track's
   * historical constant yaw of 90.
   */
  private modelYawFor(headingDeg: number): number {
    return AVATAR_YAW_DEG + entityYawDeg(headingDeg)
  }

  /**
   * Advance the hop arc while airborne. sin(π·t) starts and ends at 0,
   * and t clamps at 1, so a late "landed" patch from the server can never
   * leave the avatar hanging above the track.
   */
  private jumpArcY(dtSec: number): number {
    if (!this.airborne) return 0
    this.jumpElapsedSec += dtSec
    const t = Math.min(1, this.jumpElapsedSec / JUMP_ARC_DURATION_S)
    return this.jumpPeakM * Math.sin(Math.PI * t)
  }

  /** Read-only access to the current display arc length — used by the camera. */
  getDisplayX(): number {
    return this.displayX
  }

  /**
   * The avatar's current ground position (world XZ), projected at its real
   * lane offset — the same point `applyPose` renders it at, minus the jump
   * arc. The spectator camera frames the pack from these, so the lateral
   * spread across lanes (and a circuit's lane curvature) is honoured.
   */
  getGroundXZ(): { x: number; z: number } {
    const pose = this.projection.pose(this.displayX, this.laneOffsetM)
    return { x: pose.x, z: pose.z }
  }

  destroy(): void {
    if (!this.wrapper) return

    const clonedMats = getClonedMaterials(this.wrapper)
    if (clonedMats) for (const mat of clonedMats) safeDestroyMaterial(mat)

    disposeEntity(this.wrapper)
    this.wrapper = null
    this.anim.reset()
    this.initialized = false
    this.airborne = false
    this.jumpElapsedSec = 0
    this.jumpPeakM = JUMP_ARC_MIN_HEIGHT_M
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
