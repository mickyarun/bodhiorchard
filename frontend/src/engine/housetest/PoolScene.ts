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
 * PoolScene — Pool test scene with procedural beach chairs.
 *
 * Uses `buildBeachChair()` to create low-poly chairs from PlayCanvas
 * primitives. No GLB loading, no AABB centering, no FBX scale issues.
 * The seat height is a compile-time constant so sitting position is exact.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { buildBeachChair, SEAT_HEIGHT } from '../buildings/ProceduralBeachChair'
import { POOL_CHAIRS, type PoolChairDef } from './SceneConfig'
import { InteractableItem } from './InteractableItem'

export class PoolScene {
  private materials: MaterialFactory | null

  /** Interactable items — one per chair, for E-key sit interaction. */
  readonly items: InteractableItem[] = []

  constructor(_loader: unknown, materials: MaterialFactory | null) {
    this.materials = materials
  }

  async build(root: pc.Entity): Promise<void> {
    // Ground plane
    const ground = new pc.Entity('PoolGround')
    ground.addComponent('render', { type: 'plane' })
    ground.setLocalScale(30, 1, 30)
    if (this.materials) {
      ground.render!.meshInstances[0].material =
        this.materials.getColor('pool_ground', 0.35, 0.55, 0.25)
    }
    root.addChild(ground)

    // Pool water
    const water = new pc.Entity('PoolWater')
    water.addComponent('render', { type: 'plane' })
    water.setLocalScale(6, 1, 6)
    water.setPosition(0, 0.05, 0)
    if (this.materials) {
      water.render!.meshInstances[0].material =
        this.materials.getColor('pool_water', 0.2, 0.5, 0.8, { emissive: [0.1, 0.25, 0.4] })
    }
    root.addChild(water)

    // Place procedural beach chairs around the pool
    for (const def of POOL_CHAIRS) {
      this.placeChair(root, def)
    }

    if (import.meta.env.DEV) console.log(`[PoolScene] ${POOL_CHAIRS.length} procedural beach chairs placed, seatY=${SEAT_HEIGHT}`)
  }

  private placeChair(parent: pc.Entity, def: PoolChairDef): void {
    if (!this.materials) return

    const chair = buildBeachChair(this.materials)
    chair.setLocalPosition(def.x, 0, def.z)
    chair.setLocalEulerAngles(0, def.yaw, 0)
    parent.addChild(chair)

    // InteractableItem with EXACT known seat position — no SeatProber needed.
    // Same pattern as house interior: seat coords = placement coords.
    this.items.push(new InteractableItem(
      def.id,
      new pc.Vec3(def.x, 0, def.z),
      '[E] Sit in beach chair',
      'Relaxing by the pool...',
      'sit',
      { x: def.x, z: def.z, yaw: def.yaw, y: SEAT_HEIGHT },
      2.0,
    ))
  }
}
