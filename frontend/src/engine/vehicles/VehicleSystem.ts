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

  constructor(loader: AssetLoader, parentRoot: pc.Entity) {
    this.factory = new VehicleFactory(loader)
    this.parentRoot = parentRoot
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

    // Parent the character to the vehicle if we have their entity
    const charEntity = this.characterEntities.get(snapshot.userId)
    if (charEntity) {
      charEntity.reparent(vehicle.entity)
      charEntity.setLocalPosition(
        def.mountOffset.x / def.scale,
        def.mountOffset.y / def.scale,
        def.mountOffset.z / def.scale,
      )
      charEntity.setLocalEulerAngles(0, 0, 0)
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
    }

    this.factory.destroy(vehicle)
    this.vehicles.delete(userId)
  }

  /**
   * Clean up all vehicles on scene teardown.
   */
  destroy(): void {
    for (const [userId] of this.vehicles) {
      this.removeVehicle(userId)
    }
    this.vehicles.clear()
    this.characterEntities.clear()
  }
}
