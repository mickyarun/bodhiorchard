// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CafeteriaBuilder — Cozy outdoor eatery with a centered kitchen hut.
 *
 * Root layout (root origin = zone center, +Z points toward the viewer):
 *
 *             +z (front)
 *              ▲
 *     z=+5.0  · · ·  (far picnic row: 2 tables)
 *     z=+2.0  · · ·  (near picnic row: 2 tables)
 *     z= 0.0  [===== zone center =====]
 *     z=-0.8  [===== HUT FRONT + DOOR =====]
 *     z=-2.3  [   HUT INTERIOR (kitchen) ]
 *     z=-3.8  [===== HUT BACK WALL =========]
 *     z<-3.8  ... back garden (log stack, stumps, flowers)
 *
 * The hut geometry lives inside a `hutRoot` sub-entity offset by
 * (-HUT_WIDTH/2, 0, -HUT_DEPTH - HUT_SETBACK) so it sits centered-in-X and
 * pushed toward the back of the zone, maximising outdoor dining space and
 * filling what used to be empty grass behind the building. Outdoor furniture
 * is parented directly to `root` (local coords = zone-centered) and the back
 * garden props fill the arc behind the hut.
 *
 * Differentiators vs. the coffee bar:
 *   - Warm yellow awning + chalkboard menu + "🍽 CAFETERIA" sign
 *   - Picnic benches (not chairs) under red umbrellas
 *   - Vegetable-patch-adjacent back garden to evoke a farm-to-table vibe
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from './BuildingFactory'
import { BUILDING, CAFE, DECOR } from '../assets/AssetManifest'
import { placeScaledFurniture } from '../coffeebar/ScaledFurniture'
import { LabelRenderer } from '../rendering/LabelRenderer'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { ExclusionZone } from '../utils/MathUtils'
import { CAFETERIA_LAYOUT } from '../../../../shared/world/breakSeats'

/** Longest-axis target (metres) for café-pack props on the interior prep bar.
 *  The Coffeehouse Lounge Pack bakes node-level scale transforms so raw AABBs
 *  render 10–100× too large — placeScaledFurniture rescales them uniformly. */
const FIT_SMALL = 0.45  // fruit bowl, fancy donuts

/** Actual Kenney wall height from GLB measurement. */
const WALL_HEIGHT = 1.29
const HUT_WIDTH = 5
const HUT_DEPTH = 3
/** Center the hut in X; push the back wall toward the fence so the front
 *  yard (dining) gets the bulk of the 9-unit zone radius. */
const HUT_OFFSET_X = -HUT_WIDTH / 2
const HUT_SETBACK = 0.8
const HUT_OFFSET_Z = -HUT_DEPTH - HUT_SETBACK

/** Door trigger offset in ROOT-local coords. The single front door sits at
 *  hut-local (2.5, HUT_DEPTH); add the hut offset to get root-local. */
export const CAFETERIA_DOOR_OFFSET = {
  x: HUT_OFFSET_X + HUT_WIDTH / 2,
  z: HUT_OFFSET_Z + HUT_DEPTH,
} as const

const AWNING_YELLOW: [number, number, number] = [0.95, 0.72, 0.18]
const ROOF_TERRACOTTA: [number, number, number] = [0.52, 0.30, 0.22]
const CHALKBOARD_GREEN: [number, number, number] = [0.08, 0.28, 0.18]
const CHIMNEY_BRICK: [number, number, number] = [0.55, 0.28, 0.22]

// Picnic-table slots + bench offsets live in shared/world/breakSeats.ts
// (CAFETERIA_LAYOUT). Keeping them shared guarantees the multiplayer break
// seats line up with the benches the frontend physically renders here.

interface DecorSlot { asset: string; x: number; z: number }

/** Back-garden props that fill the arc behind the hut (root-local coords).
 *  Z values are relative to HUT_OFFSET_Z so repositioning the hut cascades
 *  automatically without touching individual rows. */
const BACK_GARDEN: ReadonlyArray<DecorSlot> = [
  { asset: BUILDING.plantSmall1, x: -3.2, z: -0.8 },
  { asset: BUILDING.plantSmall2, x:  3.2, z: -0.8 },
  { asset: DECOR.logStack,       x: -4.5, z: -1.6 },
  { asset: DECOR.stumpRound,     x:  4.5, z: -1.7 },
  { asset: DECOR.stumpOld,       x:  0.0, z: -3.2 },
  { asset: DECOR.bushRound,      x: -2.2, z: -2.9 },
  { asset: DECOR.bushGreen,      x:  2.2, z: -2.9 },
  { asset: DECOR.bushCluster,    x:  5.6, z: -4.0 },
  { asset: DECOR.bushCluster,    x: -5.6, z: -4.0 },
  { asset: DECOR.flowerYellowA,  x: -1.2, z: -1.0 },
  { asset: DECOR.flowerRedA,     x:  1.2, z: -1.0 },
  { asset: DECOR.flowerPurpleA,  x: -3.4, z: -2.4 },
  { asset: DECOR.flowerYellowB,  x:  3.4, z: -2.4 },
]

/** Perimeter plantings at the fence's interior edge (zone-centered coords). */
const SIDE_YARD: ReadonlyArray<DecorSlot> = [
  { asset: BUILDING.plantSmall1, x: -6.0, z: 0.5 },
  { asset: BUILDING.plantSmall2, x:  6.0, z: 0.5 },
  { asset: BUILDING.plantSmall1, x: -6.2, z: 4.0 },
  { asset: BUILDING.plantSmall2, x:  6.2, z: 4.0 },
  { asset: DECOR.bushRound,      x: -5.0, z: 7.0 },
  { asset: DECOR.bushRound,      x:  5.0, z: 7.0 },
]

export interface CafeteriaResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
  hutDims: { width: number; depth: number; frontDoorIndices: number[] }
  /** World-space door position (root origin + CAFETERIA_DOOR_OFFSET). */
  doorPos: { x: number; z: number }
  /** World-space hut back-left corner — physics wall colliders live here
   *  rather than at the zone center because the hut is offset inside root. */
  hutWorldOrigin: { x: number; z: number }
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

    // ─── Hut body (offset child so the hut sits centered-in-X, back half) ───
    const hut = new pc.Entity('HutBody')
    hut.setLocalPosition(HUT_OFFSET_X, 0, HUT_OFFSET_Z)
    root.addChild(hut)

    await this.factory.createFloor(hut, HUT_WIDTH, HUT_DEPTH)
    // Single centered door (index 2 of a 5-tile-wide front wall); windows on
    // the side walls and front corners for a brighter kitchen look.
    await this.factory.createWalls(hut, HUT_WIDTH, HUT_DEPTH, [
      { side: 'front', index: 0, type: 'window' },
      { side: 'front', index: 2, type: 'door' },
      { side: 'front', index: 4, type: 'window' },
      { side: 'left',  index: 1, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
    ])
    const roof = this.factory.createRoof(hut, HUT_WIDTH, HUT_DEPTH, WALL_HEIGHT)
    this.tintRoof(roof)

    // Chimney + awning + signage above the door
    this.buildChimney(hut, HUT_WIDTH - 1.2, HUT_DEPTH - 0.8, WALL_HEIGHT)
    this.buildAwning(hut, HUT_WIDTH / 2, HUT_DEPTH, WALL_HEIGHT)
    const sign = LabelRenderer.create(app, '\uD83C\uDF7D CAFETERIA', {
      fontSize: 56,
      textColor: '#FFFFFF',
      bgColor: 'rgba(45, 25, 12, 0.92)',
      borderRadius: 14,
    })
    sign.setLocalPosition(HUT_WIDTH / 2, WALL_HEIGHT + 1.1, HUT_DEPTH + 0.05)
    hut.addChild(sign)

    // Chalkboard menu mounted on the solid front-wall tile right beside the
    // door. Centred on tile index 1 (x=1.5) so it clears the window at index 0
    // and the door at index 2 — no z-fighting through the window glass.
    this.buildChalkboard(hut, 1.5, WALL_HEIGHT * 0.6, HUT_DEPTH + 0.06)

    // Potted plants flanking the door entrance
    await this.factory.placeFurniture(hut, BUILDING.pottedPlant, HUT_WIDTH / 2 - 1.2, 0, HUT_DEPTH + 0.25)
    await this.factory.placeFurniture(hut, BUILDING.pottedPlant, HUT_WIDTH / 2 + 1.0, 0, HUT_DEPTH + 0.25)

    // ─── Interior kitchen equipment against the back wall ──────────────
    // Width 5 → stove / sink / fridge / cabinet + prep counter across.
    await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenStove,   0.5, 0, 0.5)
    await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenSink,    1.5, 0, 0.5)
    await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenFridge,  2.5, 0, 0.5)
    await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenCabinet, 3.5, 0, 0.5)
    await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenCabinet, 4.5, 0, 0.5)
    // Prep counter down the middle of the kitchen
    const prepBar = await this.factory.placeFurnitureCentered(hut, BUILDING.kitchenBar, HUT_WIDTH / 2, 0, 1.6)
    const barH = BuildingFactory.getEntityHeight(prepBar)
    await this.placeScaled(app, hut, CAFE.fruitBowl,   HUT_WIDTH / 2 - 0.5, barH, 1.6, FIT_SMALL)
    await this.placeScaled(app, hut, CAFE.fancyDonuts, HUT_WIDTH / 2 + 0.4, barH, 1.6, FIT_SMALL)

    // ─── Outdoor picnic tables + benches (zone-centered coords) ────────
    // Nested loop order matches forEachBreakSeat(CAFETERIA_LAYOUT) so
    // seatIndex here aligns 1:1 with the server's BreakSeatGenerator.
    let seatIndex = 0
    for (const slot of CAFETERIA_LAYOUT.tables) {
      await this.factory.placeFurnitureCentered(root, BUILDING.tableCloth, slot.x, 0, slot.z)

      for (const bench of CAFETERIA_LAYOUT.chairs) {
        const { seat } = await this.factory.placeSeat(
          root, BUILDING.benchCushion,
          slot.x + bench.dx, slot.z + bench.dz, bench.yaw,
          'cafeteria', seatIndex++, x, z, 'benchCushion',
        )
        seats.push(seat)
      }

      // Red umbrella shade over each picnic table
      this.factory.createUmbrella(root, slot.x, slot.z, 0, 2.0, 0.85)
    }

    // ─── Back garden fills the arc BEHIND the hut; side yards line the
    // fence's interior edge. Z values in BACK_GARDEN are relative to the
    // hut's back wall so moving the hut cascades without touching rows.
    await this.placeDecorSlots(root, BACK_GARDEN, { zOffset: HUT_OFFSET_Z })
    await this.placeDecorSlots(root, SIDE_YARD)

    app.root.addChild(root)

    // ─── String lights framing the full patio ───────────────────────────
    const stringH = WALL_HEIGHT + 1.2
    this.factory.createStringLights(root, [
      // Cross string along the hut front
      { start: { x: -4.5, y: stringH, z: HUT_OFFSET_Z + HUT_DEPTH + 0.1 }, end: { x:  4.5, y: stringH, z: HUT_OFFSET_Z + HUT_DEPTH + 0.1 }, bulbCount: 6 },
      // Left perimeter — along the dining area
      { start: { x: -4.5, y: stringH, z: HUT_OFFSET_Z + HUT_DEPTH + 0.1 }, end: { x: -4.5, y: stringH, z: 7.0 }, bulbCount: 4 },
      // Right perimeter
      { start: { x:  4.5, y: stringH, z: HUT_OFFSET_Z + HUT_DEPTH + 0.1 }, end: { x:  4.5, y: stringH, z: 7.0 }, bulbCount: 4 },
      // Front cross beyond the tables
      { start: { x: -4.5, y: stringH, z: 7.0 }, end: { x:  4.5, y: stringH, z: 7.0 }, bulbCount: 6 },
    ])

    return {
      entity: root,
      exclusionZone: { x, z, radius: 9 },
      seats,
      hutDims: { width: HUT_WIDTH, depth: HUT_DEPTH, frontDoorIndices: [2] },
      doorPos: { x: x + CAFETERIA_DOOR_OFFSET.x, z: z + CAFETERIA_DOOR_OFFSET.z },
      hutWorldOrigin: { x: x + HUT_OFFSET_X, z: z + HUT_OFFSET_Z },
    }
  }

  /** Place a data-driven row of decor items at floor level (y=0). */
  private async placeDecorSlots(
    parent: pc.Entity,
    slots: ReadonlyArray<DecorSlot>,
    opts: { xOffset?: number; zOffset?: number } = {},
  ): Promise<void> {
    const dx = opts.xOffset ?? 0
    const dz = opts.zOffset ?? 0
    for (const s of slots) {
      await this.factory.placeFurniture(parent, s.asset, s.x + dx, 0, s.z + dz)
    }
  }

  /** Shorthand for the auto-scaler — keeps call sites readable. */
  private placeScaled(
    app: Application,
    parent: pc.Entity,
    asset: string,
    x: number, y: number, z: number,
    maxDim: number,
  ): ReturnType<typeof placeScaledFurniture> {
    return placeScaledFurniture(this.factory.assetLoader, app, parent, asset, x, y, z, { maxDim })
  }

  /** Swap the default roof material for a warm terracotta. */
  private tintRoof(roof: pc.Entity): void {
    const materials = this.factory.materialFactory
    if (!materials) return
    const mat = materials.getColor('cafeteria_roof', ...ROOF_TERRACOTTA, {
      metalness: 0.0,
      gloss: 0.15,
    })
    const mis = roof.render?.meshInstances ?? []
    for (const mi of mis) mi.material = mat
  }

  /** Brick chimney stack on the roof — evokes "there's a kitchen inside". */
  private buildChimney(parent: pc.Entity, cx: number, cz: number, roofY: number): void {
    const materials = this.factory.materialFactory
    if (!materials) return
    const brick = materials.getColor('cafeteria_chimney', ...CHIMNEY_BRICK, { gloss: 0.1 })

    const chimney = new pc.Entity('Chimney')
    chimney.addComponent('render', { type: 'box' })
    chimney.setLocalScale(0.55, 0.9, 0.55)
    chimney.setLocalPosition(cx, roofY + 0.45, cz)
    if (chimney.render) {
      for (const mi of chimney.render.meshInstances) mi.material = brick
    }
    parent.addChild(chimney)

    // Cap
    const cap = new pc.Entity('ChimneyCap')
    cap.addComponent('render', { type: 'box' })
    cap.setLocalScale(0.65, 0.08, 0.65)
    cap.setLocalPosition(cx, roofY + 0.93, cz)
    if (cap.render) {
      for (const mi of cap.render.meshInstances) mi.material = brick
    }
    parent.addChild(cap)
  }

  /** Yellow canopy awning over the front door. */
  private buildAwning(parent: pc.Entity, centerX: number, frontZ: number, wallHeight: number): void {
    const materials = this.factory.materialFactory
    if (!materials) return
    const yellow = materials.getColor('cafeteria_awning', ...AWNING_YELLOW, { gloss: 0.35 })
    const trim = materials.getColor('cafeteria_awning_trim', 0.48, 0.30, 0.12, { gloss: 0.4 })

    const awning = new pc.Entity('Awning')
    awning.setLocalPosition(centerX, wallHeight + 0.02, frontZ)

    const canopy = new pc.Entity('Canopy')
    canopy.addComponent('render', { type: 'box' })
    canopy.setLocalScale(2.6, 0.08, 1.0)
    canopy.setLocalPosition(0, 0, 0.48)
    canopy.setLocalEulerAngles(-8, 0, 0)
    if (canopy.render) {
      for (const mi of canopy.render.meshInstances) mi.material = yellow
    }
    awning.addChild(canopy)

    const rail = new pc.Entity('Rail')
    rail.addComponent('render', { type: 'box' })
    rail.setLocalScale(2.7, 0.14, 0.08)
    rail.setLocalPosition(0, -0.08, 0.96)
    rail.setLocalEulerAngles(-8, 0, 0)
    if (rail.render) {
      for (const mi of rail.render.meshInstances) mi.material = trim
    }
    awning.addChild(rail)

    parent.addChild(awning)
  }

  /** Chalkboard menu mounted on the front wall.
   *  Frame sits FLUSH with the wall; slate mounts ON the frame, so neither
   *  face overlaps the wall and there's no co-planar z-fight between frame
   *  and slate either. */
  private buildChalkboard(parent: pc.Entity, cx: number, cy: number, cz: number): void {
    const materials = this.factory.materialFactory
    if (!materials) return
    const slate = materials.getColor('cafeteria_chalkboard', ...CHALKBOARD_GREEN, { gloss: 0.1 })
    const frame = materials.getColor('cafeteria_chalkframe', 0.30, 0.20, 0.10, { gloss: 0.2 })

    const frameDepth = 0.05
    const boardDepth = 0.04

    const frameEntity = new pc.Entity('ChalkFrame')
    frameEntity.addComponent('render', { type: 'box' })
    frameEntity.setLocalScale(0.8, 0.6, frameDepth)
    frameEntity.setLocalPosition(cx, cy, cz + frameDepth / 2)
    if (frameEntity.render) {
      for (const mi of frameEntity.render.meshInstances) mi.material = frame
    }
    parent.addChild(frameEntity)

    const board = new pc.Entity('Chalkboard')
    board.addComponent('render', { type: 'box' })
    board.setLocalScale(0.7, 0.5, boardDepth)
    board.setLocalPosition(cx, cy, cz + frameDepth + boardDepth / 2)
    if (board.render) {
      for (const mi of board.render.meshInstances) mi.material = slate
    }
    parent.addChild(board)
  }
}
