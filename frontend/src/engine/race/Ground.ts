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
 * Ground — flat grass plane sized to frame the race track.
 *
 * Uses the same seamless grass texture as the main garden scene
 * (`assets/garden/grass.jpg`) with matching tile density so the race
 * grounds visually match the dashboard at a glance. The procedural
 * fallback colour keeps the scene from flashing untextured while the
 * JPG loads.
 *
 * Ownership:
 *   - Owns a `pc.StandardMaterial` and the uploaded grass `pc.Texture`
 *     (created from the asset once loaded). Destroys both in destroy().
 *   - Owns the `pc.Asset` registered with `app.assets` — removes it on
 *     destroy so repeat mounts don't accumulate orphaned asset records.
 *   - Does NOT destroy any material from MaterialFactory (it no longer
 *     uses one — we own ours directly because tiling + texture addressing
 *     isn't part of MaterialFactory.getColor).
 */
import * as pc from 'playcanvas'
import { disposeEntity, safeDestroyMaterial, safeDestroyTexture } from './dispose'

// Leading slash anchors at the document root so the texture loads the
// same way from `/raceview/…` as it does from `/dashboard`.
const GRASS_ASSET_URL = '/assets/garden/grass.jpg'

/** World units per grass tile. Matches GroundSystem (600 / 60 = 10). */
const GRASS_WORLD_UNITS_PER_TILE = 10

/** Fallback grass diffuse colour used before the JPG lands. */
const GRASS_FALLBACK_R = 0.45
const GRASS_FALLBACK_G = 0.65
const GRASS_FALLBACK_B = 0.35

/** Extra metres around the track on each side so the grass comfortably frames the road. */
const MARGIN_M = 20

/**
 * Grass plane sits ~5mm below the track surface so the two planes don't
 * z-fight where they visually overlap at the road edges.
 */
const Z_FIGHT_OFFSET_M = 0.005

export class Ground {
  private app: pc.AppBase
  private entity: pc.Entity | null = null
  private material: pc.StandardMaterial | null = null
  private asset: pc.Asset | null = null
  private grassTexture: pc.Texture | null = null

  constructor(app: pc.AppBase) {
    this.app = app
  }

  /**
   * @param opts.trackLengthM Race distance in metres along +X; drives ground plane length.
   * @param opts.trackWidthM  Road width in metres; ground plane widens beyond this by MARGIN_M on each side.
   */
  build(parent: pc.Entity, opts: { trackLengthM: number; trackWidthM: number }): void {
    const { trackLengthM, trackWidthM } = opts
    const length = trackLengthM + MARGIN_M * 2
    const width = trackWidthM + MARGIN_M * 2

    const entity = new pc.Entity('RaceGround')
    entity.addComponent('render', { type: 'plane' })

    const material = new pc.StandardMaterial()
    material.diffuse = new pc.Color(GRASS_FALLBACK_R, GRASS_FALLBACK_G, GRASS_FALLBACK_B)
    material.metalness = 0
    material.gloss = 0.05
    material.update()

    entity.render!.meshInstances[0].material = material

    // pc.Plane is 1×1 in local X/Z — scale to desired footprint.
    // Center along the track so x spans [-MARGIN, trackLength + MARGIN].
    entity.setLocalScale(length, 1, width)
    entity.setLocalPosition(trackLengthM / 2, -Z_FIGHT_OFFSET_M, 0)

    parent.addChild(entity)
    this.entity = entity
    this.material = material

    // Upgrade to the seamless grass JPG once it lands. Tiling matches the
    // main garden's "10 world units per tile" rhythm so the two scenes
    // share the same visual cadence.
    this.upgradeToGrassImage(length, width)
  }

  destroy(): void {
    disposeEntity(this.entity)
    this.entity = null

    safeDestroyMaterial(this.material)
    this.material = null

    safeDestroyTexture(this.grassTexture)
    this.grassTexture = null

    if (this.asset) {
      this.app.assets.remove(this.asset)
      this.asset = null
    }
  }

  private upgradeToGrassImage(lengthM: number, widthM: number): void {
    const asset = new pc.Asset('race_grass.jpg', 'texture', { url: GRASS_ASSET_URL })
    asset.once('load', () => {
      if (!this.material) return
      const tex = asset.resource as pc.Texture
      tex.addressU = pc.ADDRESS_REPEAT
      tex.addressV = pc.ADDRESS_REPEAT
      tex.minFilter = pc.FILTER_LINEAR_MIPMAP_LINEAR
      tex.magFilter = pc.FILTER_LINEAR
      tex.anisotropy = 8
      this.grassTexture = tex
      this.material.diffuseMap = tex
      this.material.diffuse = new pc.Color(1, 1, 1)
      this.material.diffuseMapTiling = new pc.Vec2(
        lengthM / GRASS_WORLD_UNITS_PER_TILE,
        widthM / GRASS_WORLD_UNITS_PER_TILE,
      )
      this.material.update()
    })
    asset.once('error', (err: string) => {
      if (import.meta.env.DEV) console.debug('[Ground] grass.jpg failed to load, keeping fallback:', err)
    })
    this.app.assets.add(asset)
    this.app.assets.load(asset)
    this.asset = asset
  }
}
