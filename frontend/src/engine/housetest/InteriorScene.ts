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
 * InteriorScene — tier-specific furnished room interior.
 *
 * Reads layout from SceneConfig.ts (data-driven). Tier determines room
 * size, furniture set, interactables, and collision boxes.
 *
 * Tier 0 (Standard): 4×4 Kenney furniture
 * Tier 1 (Hut):      3×3 KayKit basic
 * Tier 2 (Cottage):  4×4 KayKit mid-tier
 * Tier 3 (Mansion):  5×5 KayKit premium
 */
import * as pc from 'playcanvas'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { BUILDING } from '../assets/AssetManifest'
import { InteractableItem } from './InteractableItem'
import { TVEffect } from './TVEffect'
import {
  ROOM_SIZE_BY_TIER,
  getFurnitureForTier,
  getInteractablesForTier,
  getCollisionForTier,
} from './SceneConfig'
import type { CollisionBox } from './CollisionSystem'

export class InteriorScene {
  private factory: BuildingFactory
  readonly items: InteractableItem[] = []
  readonly tvEffect = new TVEffect()

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  async build(root: pc.Entity, tier = 0): Promise<CollisionBox[]> {
    this.tvEffect.init(root)
    await this.buildRoom(root, tier)
    await this.buildFurniture(root, tier)
    this.buildInteractables(tier)
    return getCollisionForTier(tier)
  }

  // ─── Room shell (sized by tier) ────────────────────────────────────────────

  private async buildRoom(root: pc.Entity, tier: number): Promise<void> {
    const room = ROOM_SIZE_BY_TIER[tier] ?? ROOM_SIZE_BY_TIER[0]

    await this.factory.createFloor(root, room.width, room.depth)

    if (tier === 0) {
      // Standard: exact original Kenney layout (hardcoded openings)
      await this.factory.createWalls(root, 4, 4, [
        { side: 'front', index: 1, type: 'door'   },
        { side: 'left',  index: 1, type: 'window' },
        { side: 'left',  index: 2, type: 'window' },
        { side: 'right', index: 1, type: 'window' },
        { side: 'right', index: 2, type: 'window' },
      ])
    } else {
      // KayKit tiers: dynamic windows
      const openings: Array<{ side: 'front' | 'back' | 'left' | 'right'; index: number; type: 'door' | 'window' }> = [
        { side: 'front', index: room.doorIndex, type: 'door' },
      ]
      for (let i = 1; i < room.depth - 1; i++) {
        openings.push({ side: 'left', index: i, type: 'window' })
        openings.push({ side: 'right', index: i, type: 'window' })
      }
      await this.factory.createWalls(root, room.width, room.depth, openings)
    }
  }

  // ─── Furniture — data-driven loop ─────────────────────────────────────────

  private async buildFurniture(root: pc.Entity, tier: number): Promise<void> {
    const furnitureDefs = getFurnitureForTier(tier)
    const heightCache = new Map<string, number>()

    for (const def of furnitureDefs) {
      let y = def.y ?? 0
      if (def.stackOn !== undefined) {
        y = heightCache.get(def.stackOn) ?? 0
      }

      const assetPath = (BUILDING as Record<string, string>)[def.asset]
      if (!assetPath) {
        console.warn(`[InteriorScene] Unknown asset key: ${def.asset}`)
        continue
      }

      const entity = await this.factory.placeFurnitureCentered(
        root, assetPath, def.x, y, def.z, def.rotation ?? 0,
      )

      // Apply scale (KayKit models are larger than Kenney)
      const s = def.scale ?? 1
      if (s !== 1) {
        entity.setLocalScale(s, s, s)
      }

      heightCache.set(def.asset, BuildingFactory.getEntityHeight(entity) * s)
    }
  }

  // ─── Interactables — data-driven loop ─────────────────────────────────────

  private buildInteractables(tier: number): void {
    const interactableDefs = getInteractablesForTier(tier)

    for (const def of interactableDefs) {
      this.items.push(new InteractableItem(
        def.id,
        new pc.Vec3(def.pos.x, 0, def.pos.z),
        def.prompt,
        def.info,
        def.action,
        def.seat,
        def.radius,
      ))
    }
  }
}
