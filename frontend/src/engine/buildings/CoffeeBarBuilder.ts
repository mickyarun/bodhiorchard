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
 * CoffeeBarBuilder — Café with a distinctive exterior and wide outdoor patio.
 *
 * Root layout (root origin = zone center, z axis points toward the viewer):
 *
 *             +z
 *              ▲
 *     z=+6.5  · · ·  (far row: 2 tables)
 *     z=+4.0  · · · · (middle row: 4 tables)
 *     z=+2.0  · · ·  (near row: 2 tables)
 *     z= 0.0  [=== HUT FRONT / DOOR ===]   ← zone center
 *     z=-1.5  [   HUT INTERIOR    ]
 *     z=-3.0  [=== HUT BACK WALL =======]
 *
 * The hut geometry lives inside a `hutRoot` sub-entity offset by
 * (−HUT_WIDTH/2, 0, −HUT_DEPTH) so the hut sits centered-in-X and pushed
 * toward the back of the zone. Outdoor furniture is parented directly to
 * root (local coords = zone-center-relative) and spreads symmetrically
 * over the full patio, filling the fenced circle.
 *
 * Café differentiators vs. a generic house:
 *   - Single entrance with a red-striped awning over the door
 *   - "COFFEE" billboard sign above the awning
 *   - Potted plants flanking the entrance
 *   - Red umbrellas over every outdoor table
 *   - Warm terracotta roof instead of the default grey
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from './BuildingFactory'
import { BUILDING } from '../assets/AssetManifest'
import { LabelRenderer } from '../rendering/LabelRenderer'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { ExclusionZone } from '../utils/MathUtils'
import { COFFEE_BAR_LAYOUT } from '../../../../shared/world/breakSeats'

const WALL_HEIGHT = 1.29
const HUT_WIDTH = 5
const HUT_DEPTH = 3
/** Shift the hut so its width is centered on the zone and its footprint is
 *  pushed toward the back, leaving a clear walking path in front of the door.
 *  The extra 0.8 past -HUT_DEPTH backs the building off the door zone. */
const HUT_OFFSET_X = -HUT_WIDTH / 2
const HUT_SETBACK = 0.8
const HUT_OFFSET_Z = -HUT_DEPTH - HUT_SETBACK
/** Door world position relative to zone center (root-local z of the front
 *  wall). Kept in sync with HUT_OFFSET_Z so GardenEngine can compute the
 *  door trigger and exit spawn without reaching into the builder. */
export const COFFEE_DOOR_LOCAL_Z = HUT_OFFSET_Z + HUT_DEPTH

const AWNING_RED: [number, number, number] = [0.82, 0.18, 0.12]
const ROOF_TERRACOTTA: [number, number, number] = [0.55, 0.28, 0.18]

// Table slots, chair offsets, and seat Y live in shared/world/breakSeats.ts —
// imported above as COFFEE_BAR_LAYOUT so the multiplayer seat generator
// renders remote members onto the exact same chairs we build here.

export interface CoffeeBarResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
  hutDims: { width: number; depth: number; frontDoorIndices: number[] }
  /** World position of the hut's back-left corner — used for physics wall
   *  colliders. Differs from the zone center because the hut is offset
   *  inside the coffee-bar root. */
  hutWorldOrigin: { x: number; z: number }
}

export class CoffeeBarBuilder {
  private factory: BuildingFactory

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  async build(app: Application, x: number, z: number): Promise<CoffeeBarResult> {
    const root = new pc.Entity('CoffeeBar')
    root.setPosition(x, 0, z)

    const seats: InteractionPoint[] = []

    // ─── Hut body (offset child so the hut sits centered-in-X, back half) ───
    const hut = new pc.Entity('HutBody')
    hut.setLocalPosition(HUT_OFFSET_X, 0, HUT_OFFSET_Z)
    root.addChild(hut)

    await this.factory.createFloor(hut, HUT_WIDTH, HUT_DEPTH)
    await this.factory.createWalls(hut, HUT_WIDTH, HUT_DEPTH, [
      { side: 'front', index: 0, type: 'window' },
      { side: 'front', index: 1, type: 'window' },
      { side: 'front', index: 2, type: 'door' },
      { side: 'front', index: 3, type: 'window' },
      { side: 'front', index: 4, type: 'window' },
      { side: 'left', index: 1, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
    ])
    const roof = this.factory.createRoof(hut, HUT_WIDTH, HUT_DEPTH, WALL_HEIGHT)
    this.tintRoof(roof)

    // Awning + sign above the single door (hut-local coords)
    this.buildAwning(hut, HUT_WIDTH / 2, HUT_DEPTH, WALL_HEIGHT)
    const sign = LabelRenderer.create(app, '\u2615 COFFEE', {
      fontSize: 56,
      textColor: '#FFFFFF',
      bgColor: 'rgba(55, 30, 15, 0.92)',
      borderRadius: 14,
    })
    sign.setLocalPosition(HUT_WIDTH / 2, WALL_HEIGHT + 1.05, HUT_DEPTH + 0.05)
    hut.addChild(sign)

    // Potted plants flanking the entrance
    await this.factory.placeFurniture(hut, BUILDING.pottedPlant, HUT_WIDTH / 2 - 1.1, 0, HUT_DEPTH + 0.35)
    await this.factory.placeFurniture(hut, BUILDING.pottedPlant, HUT_WIDTH / 2 + 0.9, 0, HUT_DEPTH + 0.35)

    // ─── Interior back-wall equipment (hut-local coords) ───────────────
    await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenCabinet, 0.5, 0, 0.5)
    await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenCabinet, 1.5, 0, 0.5)
    const bar = await this.factory.placeFurnitureCentered(
      hut, BUILDING.kitchenBar, HUT_WIDTH / 2, 0, 0.7,
    )
    const barHeight = BuildingFactory.getEntityHeight(bar)
    await this.factory.placeFurnitureCentered(
      hut, BUILDING.kitchenCoffeeMachine, HUT_WIDTH / 2, barHeight, 0.7,
    )
    await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenStove, 3.5, 0, 0.5)
    await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenCabinet, 4.5, 0, 0.5)

    // ─── Outdoor tables (parented to root — zone-centered coords) ──────
    // Nested loop matches forEachBreakSeat(COFFEE_BAR_LAYOUT) order, so the
    // seatIndex counter here lines up 1:1 with the server's BreakSeatGenerator.
    let seatIndex = 0
    for (const slot of COFFEE_BAR_LAYOUT.tables) {
      await this.factory.placeFurnitureCentered(root, BUILDING.tableCoffee, slot.x, 0, slot.z)
      for (const chair of COFFEE_BAR_LAYOUT.chairs) {
        const { seat } = await this.factory.placeSeat(
          root, BUILDING.chairCushion,
          slot.x + chair.dx, slot.z + chair.dz, chair.yaw,
          'coffee_bar', seatIndex++, x, z,
          'chairCushion', 'interact-right',
        )
        seats.push(seat)
      }
      this.factory.createUmbrella(root, slot.x, slot.z, 0, 1.9, 0.75)
    }

    // Decorative plants at the patio perimeter
    await this.factory.placeFurniture(root, BUILDING.plantSmall1, -5.3, 0, 2.0)
    await this.factory.placeFurniture(root, BUILDING.plantSmall2,  5.3, 0, 2.0)
    await this.factory.placeFurniture(root, BUILDING.plantSmall1, -5.3, 0, 5.5)
    await this.factory.placeFurniture(root, BUILDING.plantSmall2,  5.3, 0, 5.5)
    await this.factory.placeFurniture(root, BUILDING.plantSmall1, -3.0, 0, 7.2)
    await this.factory.placeFurniture(root, BUILDING.plantSmall2,  3.0, 0, 7.2)

    app.root.addChild(root)

    // String lights framing the full patio (zone-centered coords)
    const stringH = WALL_HEIGHT + 1.2
    this.factory.createStringLights(root, [
      // Hut-front cross (just outside the door, spans the hut width + a bit)
      { start: { x: -5.0, y: stringH, z: 0.2 }, end: { x:  5.0, y: stringH, z: 0.2 }, bulbCount: 5 },
      // Left perimeter
      { start: { x: -5.0, y: stringH, z: 0.2 }, end: { x: -5.0, y: stringH, z: 7.0 }, bulbCount: 4 },
      // Right perimeter
      { start: { x:  5.0, y: stringH, z: 0.2 }, end: { x:  5.0, y: stringH, z: 7.0 }, bulbCount: 4 },
      // Front cross
      { start: { x: -5.0, y: stringH, z: 7.0 }, end: { x:  5.0, y: stringH, z: 7.0 }, bulbCount: 5 },
    ])

    return {
      entity: root,
      exclusionZone: { x, z, radius: 8 },
      seats,
      hutDims: { width: HUT_WIDTH, depth: HUT_DEPTH, frontDoorIndices: [2] },
      hutWorldOrigin: { x: x + HUT_OFFSET_X, z: z + HUT_OFFSET_Z },
    }
  }

  /** Swap the default roof material for a warm terracotta. */
  private tintRoof(roof: pc.Entity): void {
    const materials = this.factory.materialFactory
    if (!materials) return
    const mat = materials.getColor('coffee_roof', ...ROOF_TERRACOTTA, {
      metalness: 0.0,
      gloss: 0.15,
    })
    const mis = roof.render?.meshInstances ?? []
    for (const mi of mis) mi.material = mat
  }

  /**
   * Awning canopy over the door: slightly-tilted red panel + darker trim rail.
   * Purely decorative — no collider, no interaction.
   */
  private buildAwning(parent: pc.Entity, centerX: number, frontZ: number, wallHeight: number): void {
    const materials = this.factory.materialFactory
    if (!materials) return

    const red = materials.getColor('awning_red', ...AWNING_RED, { gloss: 0.35 })
    const trim = materials.getColor('awning_trim', 0.35, 0.08, 0.05, { gloss: 0.4 })

    const awning = new pc.Entity('Awning')
    awning.setLocalPosition(centerX, wallHeight + 0.02, frontZ)

    const canopy = new pc.Entity('Canopy')
    canopy.addComponent('render', { type: 'box' })
    canopy.setLocalScale(2.5, 0.08, 0.95)
    canopy.setLocalPosition(0, 0, 0.45)
    canopy.setLocalEulerAngles(-8, 0, 0)
    if (canopy.render) {
      for (const mi of canopy.render.meshInstances) mi.material = red
    }
    awning.addChild(canopy)

    const rail = new pc.Entity('Rail')
    rail.addComponent('render', { type: 'box' })
    rail.setLocalScale(2.6, 0.14, 0.08)
    rail.setLocalPosition(0, -0.08, 0.9)
    rail.setLocalEulerAngles(-8, 0, 0)
    if (rail.render) {
      for (const mi of rail.render.meshInstances) mi.material = trim
    }
    awning.addChild(rail)

    parent.addChild(awning)
  }
}
