/**
 * VehicleFactory — Loads and instantiates vehicle GLBs.
 *
 * Uses the shared AssetLoader for caching/dedup. Creates vehicle
 * entities with animation state graph and correct scaling.
 *
 * The rider character is parented to the vehicle at the mount offset.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { VehicleDef } from './VehicleManifest'
import { findAnimTrack, type ContainerWithAnims } from '../characters/AnimUtils'

export interface VehicleEntity {
  entity: pc.Entity
  def: VehicleDef
}

/**
 * Anim state graph for vehicles: Idle ↔ Walk ↔ Gallop.
 * Driven by a single "speed" integer parameter:
 *   0 = Idle, 1 = Walk, 2 = Gallop
 */
const VEHICLE_STATE_GRAPH = {
  layers: [{
    name: 'locomotion',
    states: [
      { name: 'START' },
      { name: 'Idle', speed: 1.0 },
      { name: 'Walk', speed: 1.0 },
      { name: 'Gallop', speed: 1.0 },
    ],
    transitions: [
      { from: 'START', to: 'Idle', time: 0, priority: 0 },
      {
        from: 'Idle', to: 'Walk', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_GREATER_THAN, value: 0 }],
      },
      {
        from: 'Walk', to: 'Idle', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_LESS_THAN_EQUAL_TO, value: 0 }],
      },
      {
        from: 'Walk', to: 'Gallop', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_GREATER_THAN, value: 1 }],
      },
      {
        from: 'Gallop', to: 'Walk', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_LESS_THAN_EQUAL_TO, value: 1 }],
      },
      {
        from: 'Gallop', to: 'Idle', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_LESS_THAN_EQUAL_TO, value: 0 }],
      },
    ],
  }],
  parameters: {
    speed: { name: 'speed', type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
  },
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
    const container = asset.resource as ContainerWithAnims
    const entity = container.instantiateRenderEntity()

    entity.name = `Vehicle_${def.id}`
    entity.setLocalScale(def.scale, def.scale, def.scale)
    entity.setPosition(x, 0, z)
    entity.setEulerAngles(0, yaw, 0)

    // Set up anim component with vehicle state graph (Idle ↔ Walk ↔ Gallop)
    entity.addComponent('anim', { activate: true })
    entity.anim!.loadStateGraph(VEHICLE_STATE_GRAPH)

    // Assign animation tracks from the GLB container to state graph nodes
    const layer = entity.anim!.baseLayer
    for (const [stateName, clipName] of Object.entries(def.animations)) {
      const track = findAnimTrack(container, clipName)
      if (track && layer) {
        // State names in the graph are capitalized: Idle, Walk, Gallop
        const graphState = stateName.charAt(0).toUpperCase() + stateName.slice(1)
        layer.assignAnimation(graphState, track)
      }
    }

    return { entity, def }
  }

  /**
   * Destroy a vehicle entity and clean up resources.
   */
  destroy(vehicle: VehicleEntity): void {
    vehicle.entity.destroy()
  }
}
