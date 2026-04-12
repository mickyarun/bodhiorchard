/**
 * VehicleFactory — Loads and instantiates vehicle GLBs.
 *
 * Uses the shared AssetLoader for caching/dedup. Creates vehicle
 * entities with animation components and correct scaling.
 *
 * The rider character is parented to the vehicle at the mount offset.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { VehicleDef } from './VehicleManifest'

export interface VehicleEntity {
  entity: pc.Entity
  def: VehicleDef
}

export class VehicleFactory {
  private loader: AssetLoader

  constructor(loader: AssetLoader) {
    this.loader = loader
  }

  /**
   * Preload the vehicle GLB so instantiation is instant.
   */
  async preload(def: VehicleDef): Promise<void> {
    await this.loader.load(def.glb)
  }

  /**
   * Create a vehicle entity at the given world position.
   * Returns the entity with animations ready to play.
   */
  async create(def: VehicleDef, x: number, z: number, yaw: number): Promise<VehicleEntity> {
    const asset = await this.loader.load(def.glb)
    const entity = this.loader.instance(asset)

    entity.name = `Vehicle_${def.id}`
    entity.setLocalScale(def.scale, def.scale, def.scale)
    entity.setPosition(x, 0, z)
    entity.setEulerAngles(0, yaw, 0)

    // Set up animation component if the asset has animations
    const animComponent = entity.anim
    if (animComponent) {
      // Play idle by default
      this.playAnimation(entity, def.animations.idle)
    }

    return { entity, def }
  }

  /**
   * Play a named animation on the vehicle entity.
   * Handles the case where animations are embedded in the container asset.
   */
  playAnimation(entity: pc.Entity, animName: string, _loop = true): void {
    const anim = entity.anim
    if (!anim) return

    // Container assets store animations as named clips
    // Try to play by name
    try {
      anim.baseLayer?.transition(animName, 0.2)
    } catch {
      // Animation state graph not configured for this clip name; silently ignore.
    }
  }

  /**
   * Destroy a vehicle entity and clean up resources.
   */
  destroy(vehicle: VehicleEntity): void {
    vehicle.entity.destroy()
  }
}
