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
import { getVehicleDef } from './VehicleManifest'
import type { AssetLoader } from '../assets/AssetLoader'

export interface VehicleSnapshot {
  userId: string
  vehicleId: string  // empty = on foot
  x: number
  z: number
  yaw: number
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
      // Update: move existing vehicle
      existingVehicle.entity.setPosition(snapshot.x, 0, snapshot.z)
      existingVehicle.entity.setEulerAngles(0, snapshot.yaw, 0)
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
  }
}
