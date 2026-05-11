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
 * VehicleSystem — Syncs remote players' vehicle state.
 *
 * Follows the engine's "one system per concern" pattern (like
 * CharacterSystem, AgentCharacterSystem, GardenAnimalSystem).
 *
 * Observes MemberState.vehicleId changes for remote players:
 *   - Non-empty vehicleId → spawn vehicle entity, parent character to it
 *   - Empty vehicleId → destroy vehicle entity, unparent character
 *
 * Does NOT handle the local player (that's VehicleController via TakeoverController).
 */
import * as pc from 'playcanvas'
import { VehicleFactory, type VehicleEntity } from './VehicleFactory'
import { getVehicleDef, type VehicleDef } from './VehicleManifest'
import type { AssetLoader } from '../assets/AssetLoader'
import { lerpPose, POSITION_LERP, type PoseState } from '../multiplayer/RemoteInterp'

export interface VehicleSnapshot {
  userId: string
  vehicleId: string  // empty = on foot
  x: number
  z: number
  yaw: number
}

/**
 * Per-vehicle interpolation + anim-state record. Extends the shared PoseState
 * with vehicle-specific bookkeeping (last update time + applied gait).
 */
interface MotionSample extends PoseState {
  /** performance.now() ms when the target was last updated. */
  t: number
  /** Last applied anim `speed` (0/1/2) — avoids redundant setInteger calls. */
  lastSpeed: number
  /** Cached gait thresholds for this vehicle (computed once at spawn). */
  thresholds: { idleMax: number; walkMax: number }
}

/**
 * Colyseus only broadcasts patches when state changes. When a rider stops
 * moving, no new position snapshot arrives for the horse — so updateVehicle-
 * Animation can't re-evaluate. If the last sample is older than this
 * threshold, the per-frame update() force-transitions the horse to Idle.
 */
const STALE_SAMPLE_MS = 150

/**
 * Assumed base walking speed (m/s) when a vehicle def doesn't declare explicit
 * gait thresholds. Matches TakeoverController's WALK_SPEED — the horse's
 * `speedMultiplier` scales this to its walk speed, and gallop is 2× walk.
 */
const BASE_WALK_SPEED = 3.0

/** Derive gait velocity thresholds for a vehicle. Uses def overrides if set. */
function resolveGaitThresholds(def: VehicleDef): { idleMax: number; walkMax: number } {
  if (def.gaitThresholds) return def.gaitThresholds
  const walkSpeed = BASE_WALK_SPEED * def.speedMultiplier
  // idleMax: dead-band just above zero so 20Hz jitter doesn't flicker idle↔walk
  // walkMax: midpoint between walk and gallop (2× walk)
  return { idleMax: walkSpeed * 0.1, walkMax: walkSpeed * 1.5 }
}

export class VehicleSystem {
  private factory: VehicleFactory
  private parentRoot: pc.Entity
  private vehicles = new Map<string, VehicleEntity>()
  /** Prevents concurrent spawns for the same user during async GLB load. */
  private pendingSpawns = new Set<string>()
  /** Character entities by userId — provided by CharacterSystem for parenting. */
  private characterEntities = new Map<string, pc.Entity>()
  /** Local user ID to skip — their vehicle is handled by VehicleController. */
  private localUserId: string | null = null
  /** Set of userIds currently mounted — used by CharacterSystem to skip position updates. */
  private mountedUsers = new Set<string>()
  /** Last position sample per user for deriving horse gait from snapshot delta. */
  private motionSamples = new Map<string, MotionSample>()

  constructor(loader: AssetLoader, parentRoot: pc.Entity) {
    this.factory = new VehicleFactory(loader)
    this.parentRoot = parentRoot
  }

  /** Set the local user ID — VehicleSystem will skip this user entirely. */
  setLocalUserId(userId: string | null): void {
    this.localUserId = userId
  }

  /** Check if a user is currently mounted on a vehicle (for CharacterSystem). */
  isMounted(userId: string): boolean {
    return this.mountedUsers.has(userId)
  }

  /**
   * Register a character entity so the vehicle system knows which
   * entity to parent when a remote player mounts a vehicle.
   */
  registerCharacter(userId: string, entity: pc.Entity): void {
    this.characterEntities.set(userId, entity)
  }

  /**
   * Unregister a character entity when it's removed from the scene.
   */
  unregisterCharacter(userId: string): void {
    this.characterEntities.delete(userId)
    // Also clean up any vehicle for this user
    this.removeVehicle(userId)
  }

  /**
   * Update vehicle state from server snapshot.
   * Called each frame or on snapshot change.
   */
  async updateFromSnapshot(snapshot: VehicleSnapshot): Promise<void> {
    if (snapshot.userId === this.localUserId) return
    const existingVehicle = this.vehicles.get(snapshot.userId)

    if (snapshot.vehicleId && !existingVehicle) {
      // Mount: spawn vehicle for this remote player (guard against concurrent spawns)
      if (this.pendingSpawns.has(snapshot.userId)) return
      this.pendingSpawns.add(snapshot.userId)
      try { await this.spawnVehicle(snapshot) }
      finally { this.pendingSpawns.delete(snapshot.userId) }
    } else if (!snapshot.vehicleId && existingVehicle) {
      // Dismount: remove vehicle
      this.removeVehicle(snapshot.userId)
    } else if (snapshot.vehicleId && existingVehicle) {
      // Update: record target + drive anim state. Actual transform application
      // is lerped in the per-frame update() loop so 20Hz snapshots don't cause
      // visible flicker between frames.
      this.updateVehicleAnimation(snapshot, existingVehicle)
    }
  }

  /**
   * Per-frame tick. Two responsibilities:
   *   1. Lerp each remote horse's transform from its last-applied pose toward
   *      the server-authoritative target. Without this the horse snaps 20×/s
   *      to discrete snapshot poses, which reads as flicker during a gallop.
   *   2. Force stopped horses back to Idle — Colyseus only broadcasts patches
   *      on state change, so when the rider stops moving no new snapshot
   *      arrives and the velocity-from-delta code inside updateFromSnapshot
   *      never runs, leaving the horse stuck in Walk/Gallop forever.
   */
  update(): void {
    const now = performance.now()
    for (const [userId, sample] of this.motionSamples) {
      const vehicle = this.vehicles.get(userId)
      if (!vehicle) continue

      // (1) Position + yaw lerp. Shared interp helper — never reads back from
      // the entity (the anim component may write the horse's transform
      // between ticks, which would destabilise the lerp source).
      lerpPose(sample, POSITION_LERP)
      vehicle.entity.setPosition(sample.currentX, sample.currentY, sample.currentZ)
      vehicle.entity.setEulerAngles(0, sample.currentYaw, 0)

      // (2) Force-idle if no snapshot arrived recently.
      if (sample.lastSpeed !== 0 && now - sample.t >= STALE_SAMPLE_MS) {
        const anim = vehicle.entity.anim
        if (anim) {
          anim.setInteger('speed', 0)
          sample.lastSpeed = 0
        }
      }
    }
  }

  /**
   * Derive the horse's gait (Idle/Walk/Gallop) from position delta between
   * server snapshots and apply it to the anim component. Server only
   * broadcasts position/yaw for vehicles; the gait has to be estimated
   * client-side.
   */
  private updateVehicleAnimation(
    snapshot: VehicleSnapshot,
    vehicle: VehicleEntity,
  ): void {
    const anim = vehicle.entity.anim
    if (!anim) return

    const now = performance.now()
    const prev = this.motionSamples.get(snapshot.userId)

    let desiredSpeed: number
    const thresholds = prev?.thresholds ?? resolveGaitThresholds(vehicle.def)
    if (!prev) {
      // First sample — no delta to compute yet; stay in Idle.
      desiredSpeed = 0
    } else {
      const dt = (now - prev.t) / 1000  // seconds
      if (dt <= 0) return  // duplicate tick; skip
      const dx = snapshot.x - prev.targetX
      const dz = snapshot.z - prev.targetZ
      const velocity = Math.sqrt(dx * dx + dz * dz) / dt

      if (velocity < thresholds.idleMax) desiredSpeed = 0
      else if (velocity < thresholds.walkMax) desiredSpeed = 1
      else desiredSpeed = 2
    }

    if (!prev || prev.lastSpeed !== desiredSpeed) {
      anim.setInteger('speed', desiredSpeed)
    }

    // Mutate in place if we have a prior sample — saves a per-patch allocation
    // at 20Hz × N mounted users. First sample seeds current* from the entity's
    // spawn pose so the lerp doesn't fly in from (0,0,0).
    if (prev) {
      prev.targetX = snapshot.x
      prev.targetY = 0
      prev.targetZ = snapshot.z
      prev.targetYaw = snapshot.yaw
      prev.t = now
      prev.lastSpeed = desiredSpeed
    } else {
      const pos = vehicle.entity.getPosition()
      const yaw = vehicle.entity.getEulerAngles().y
      this.motionSamples.set(snapshot.userId, {
        targetX: snapshot.x,
        targetY: 0,
        targetZ: snapshot.z,
        targetYaw: snapshot.yaw,
        currentX: pos.x,
        currentY: pos.y,
        currentZ: pos.z,
        currentYaw: yaw,
        t: now,
        lastSpeed: desiredSpeed,
        thresholds,
      })
    }
  }

  private async spawnVehicle(snapshot: VehicleSnapshot): Promise<void> {
    const def = getVehicleDef(snapshot.vehicleId)
    if (!def) return

    const vehicle = await this.factory.create(def, snapshot.x, snapshot.z, snapshot.yaw)
    this.parentRoot.addChild(vehicle.entity)
    this.vehicles.set(snapshot.userId, vehicle)
    this.mountedUsers.add(snapshot.userId)

    // Parent the character to the vehicle if we have their entity.
    // The vehicle is scaled to def.scale (e.g. 0.45), so we must
    // counter-scale the character to keep it at world-scale 1.0.
    const charEntity = this.characterEntities.get(snapshot.userId)
    if (charEntity) {
      const inv = 1 / def.scale
      charEntity.reparent(vehicle.entity)
      charEntity.setLocalPosition(
        def.mountOffset.x * inv,
        def.mountOffset.y * inv,
        def.mountOffset.z * inv,
      )
      charEntity.setLocalScale(inv, inv, inv)
      charEntity.setLocalEulerAngles(0, 0, 0)
      // Freeze character in idle pose while mounted
      const anim = charEntity.anim
      if (anim) {
        anim.setInteger('speed', 0)
        anim.setBoolean('sitting', false)
      }
    }
  }

  private removeVehicle(userId: string): void {
    const vehicle = this.vehicles.get(userId)
    if (!vehicle) return

    // Unparent the character back to the scene root
    const charEntity = this.characterEntities.get(userId)
    if (charEntity && charEntity.parent === vehicle.entity) {
      const pos = vehicle.entity.getPosition()
      charEntity.reparent(this.parentRoot)
      charEntity.setPosition(pos.x, 0, pos.z)
      charEntity.setLocalScale(1, 1, 1)
      // Restore character animation
      const anim = charEntity.anim
      if (anim) {
        anim.setBoolean('sitting', false)
        anim.setInteger('speed', 0)
      }
    }

    this.factory.destroy(vehicle)
    this.vehicles.delete(userId)
    this.mountedUsers.delete(userId)
    this.motionSamples.delete(userId)
  }

  /**
   * Clean up all vehicles on scene teardown.
   */
  destroy(): void {
    for (const userId of [...this.vehicles.keys()]) {
      this.removeVehicle(userId)
    }
    this.vehicles.clear()
    this.characterEntities.clear()
    this.motionSamples.clear()
  }
}
