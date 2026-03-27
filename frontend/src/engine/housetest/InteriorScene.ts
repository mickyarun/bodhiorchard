/**
 * InteriorScene — furnished room interior.
 *
 * Reads layout from SceneConfig.ts (data-driven). This class only contains
 * building logic — no furniture positions or collision values inline.
 *
 * Room shell: 4×4 Kenney tiles, no roof (camera looks down from above).
 * Door exit at front wall (Z=4), gap at X=1.0–2.0 mirroring the exterior.
 */
import * as pc from 'playcanvas'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { BUILDING } from '../assets/AssetManifest'
import { InteractableItem } from './InteractableItem'
import { TVEffect } from './TVEffect'
import {
  INTERIOR_FURNITURE,
  INTERIOR_INTERACTABLES,
  INTERIOR_COLLISION,
} from './SceneConfig'
import type { CollisionBox } from './CollisionSystem'

export class InteriorScene {
  private factory: BuildingFactory
  readonly items: InteractableItem[] = []
  readonly tvEffect = new TVEffect()

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  async build(root: pc.Entity): Promise<CollisionBox[]> {
    this.tvEffect.init(root)
    await this.buildRoom(root)
    await this.buildFurniture(root)
    this.buildInteractables()
    return INTERIOR_COLLISION
  }

  // ─── Room shell ────────────────────────────────────────────────────────────

  private async buildRoom(root: pc.Entity): Promise<void> {
    await this.factory.createFloor(root, 4, 4)
    await this.factory.createWalls(root, 4, 4, [
      { side: 'front', index: 1, type: 'door'   },
      { side: 'left',  index: 1, type: 'window' },
      { side: 'left',  index: 2, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
      { side: 'right', index: 2, type: 'window' },
    ])
  }

  // ─── Furniture — data-driven loop ─────────────────────────────────────────

  private async buildFurniture(root: pc.Entity): Promise<void> {
    // heightCache: asset key → entity height, used for stackOn resolution.
    const heightCache = new Map<string, number>()

    for (const def of INTERIOR_FURNITURE) {
      // Resolve y: floor level by default, or top of the stacked-upon item.
      let y = def.y ?? 0
      if (def.stackOn !== undefined) {
        y = heightCache.get(def.stackOn) ?? 0
      }

      const assetPath = (BUILDING as Record<string, string>)[def.asset]
      const entity = await this.factory.placeFurnitureCentered(
        root, assetPath, def.x, y, def.z, def.rotation ?? 0,
      )

      // Cache height so subsequent items can stack on this one.
      heightCache.set(def.asset, BuildingFactory.getEntityHeight(entity))
    }
  }

  // ─── Interactables — data-driven loop ─────────────────────────────────────

  private buildInteractables(): void {
    for (const def of INTERIOR_INTERACTABLES) {
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
