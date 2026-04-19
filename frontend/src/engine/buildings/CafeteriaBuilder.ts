// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CafeteriaBuilder — Cafeteria with enclosed kitchen hut + outdoor dining.
 *
 * A small kitchen hut (4×2 tiles) with walls and roof houses cooking
 * equipment. Long tables with benches sit outside for communal dining.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from './BuildingFactory'
import { BUILDING } from '../assets/AssetManifest'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { ExclusionZone } from '../utils/MathUtils'

/** Actual Kenney wall height from GLB measurement. */
const WALL_HEIGHT = 1.29
const HUT_WIDTH = 4
const HUT_DEPTH = 2

/**
 * Door trigger position in root-local coords. The front wall lives at
 * local z = HUT_DEPTH (=2); the two door tiles span local x = [1, 3], so the
 * centerline sits at x = 2. Exported so GardenEngine can compute the
 * interior-transition trigger without reaching into the builder internals.
 */
export const CAFETERIA_DOOR_OFFSET = { x: 2, z: HUT_DEPTH } as const

export interface CafeteriaResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
  /** Hut dimensions for takeover physics wall generation. */
  hutDims: { width: number; depth: number; frontDoorIndices: number[] }
  /** World-space door position — zone center + CAFETERIA_DOOR_OFFSET. */
  doorPos: { x: number; z: number }
}

export class CafeteriaBuilder {
  private factory: BuildingFactory

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  async build(app: Application, x: number, z: number): Promise<CafeteriaResult> {
    const root = new pc.Entity('Cafeteria')
    root.setPosition(x, 0, z)

    const seats: InteractionPoint[] = []

    // ─── Kitchen hut (4×2 tiles, open front for serving) ───
    await this.factory.createFloor(root, 4, 2)

    await this.factory.createWalls(root, 4, 2, [
      { side: 'front', index: 1, type: 'door' },
      { side: 'front', index: 2, type: 'door' },
      { side: 'left', index: 0, type: 'window' },
      { side: 'right', index: 0, type: 'window' },
    ])

    this.factory.createRoof(root, 4, 2, WALL_HEIGHT)

    // Kitchen appliances against back wall — independent pieces, use centered placement
    // Positioned in back half of 4×2 hut (z ≈ 0.5 centers them between back wall and hut middle)
    await this.factory.placeFurnitureCentered(root, BUILDING.kitchenStove, 0.5, 0, 0.5)
    await this.factory.placeFurnitureCentered(root, BUILDING.kitchenSink, 1.5, 0, 0.5)
    await this.factory.placeFurnitureCentered(root, BUILDING.kitchenFridge, 2.5, 0, 0.5)
    await this.factory.placeFurnitureCentered(root, BUILDING.kitchenCabinet, 3.5, 0, 0.5)

    // ─── Outdoor dining (in front of kitchen) ───
    // Two rows of long tables with benches on each side, properly spaced
    let seatIndex = 0
    const benchOffset = 0.55 // distance from table center to bench AABB center

    for (let row = 0; row < 2; row++) {
      const tz = 3.5 + row * 2.8

      // Two tables side by side (each ~1 unit wide) — same model for consistent alignment
      await this.factory.placeFurnitureCentered(root, BUILDING.tableCloth, 1.0, 0, tz)
      await this.factory.placeFurnitureCentered(root, BUILDING.tableCloth, 3.0, 0, tz)

      // Benches snug against table on both sides
      // Model front faces +Z after centering — flip so each bench faces the table
      for (const side of [-1, 1]) {
        const bz = tz + side * benchOffset
        const facing = side > 0 ? 180 : 0 // +1 side faces -Z toward table, -1 side faces +Z toward table

        const bench1 = await this.factory.placeSeat(root, BUILDING.benchCushion, 1.0, bz, facing, 'cafeteria', seatIndex++, x, z, 'benchCushion')
        const bench2 = await this.factory.placeSeat(root, BUILDING.benchCushion, 3.0, bz, facing, 'cafeteria', seatIndex++, x, z, 'benchCushion')
        seats.push(bench1.seat, bench2.seat)
      }
    }

    app.root.addChild(root)

    // ─── String lights (local coords, part of building entity) ───
    const stringH = WALL_HEIGHT + 1.2
    this.factory.createStringLights(root, [
      // Left side of dining area
      { start: { x: -1, y: stringH, z: HUT_DEPTH }, end: { x: -1, y: stringH, z: 7.5 }, bulbCount: 3 },
      // Right side of dining area
      { start: { x: HUT_WIDTH + 1, y: stringH, z: HUT_DEPTH }, end: { x: HUT_WIDTH + 1, y: stringH, z: 7.5 }, bulbCount: 3 },
      // Cross-string at hut front
      { start: { x: -1, y: stringH, z: HUT_DEPTH }, end: { x: HUT_WIDTH + 1, y: stringH, z: HUT_DEPTH }, bulbCount: 3 },
    ])

    return {
      entity: root,
      exclusionZone: { x, z, radius: 9 },
      seats,
      hutDims: { width: HUT_WIDTH, depth: HUT_DEPTH, frontDoorIndices: [1, 2] },
      doorPos: { x: x + CAFETERIA_DOOR_OFFSET.x, z: z + CAFETERIA_DOOR_OFFSET.z },
    }
  }
}
