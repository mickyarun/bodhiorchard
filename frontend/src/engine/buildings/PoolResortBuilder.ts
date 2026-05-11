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
 * PoolResortBuilder — Pool area with procedural water, sandstone deck,
 * diving board, ladder, beach loungers, umbrellas, and poolside trees.
 *
 * Layout (root origin = zone center, +Z toward viewer):
 *
 *            +z  (pool entrance from main path)
 *             ▲
 *    lounger row along +z (2 chairs under shared umbrella)
 *             ┌──────────────┐
 *    chairs → │    POOL      │ ← chairs
 *             │  6m x 6m     │
 *             └──────────────┘
 *    diving board at -z (opposite the entrance)
 *
 * All positions are in SLOT constants at the top of the file so adding a
 * chair, umbrella, tree, side table, or bush is a one-line edit.
 *
 * The deck is a 4-piece picture frame (not a solid cylinder) so water stays
 * visible in the middle — a solid deck would render through the translucent
 * water plane as a muddy tint (water opacity is 0.7 in WaterSurface).
 */
import * as pc from "playcanvas"
import type { Application } from "../core/Application"
import { BuildingFactory } from "./BuildingFactory"
import { buildBeachChair, SEAT_HEIGHT } from "./ProceduralBeachChair"
import type { AssetLoader } from "../assets/AssetLoader"
import type { MaterialFactory } from "../rendering/MaterialFactory"
import type { InteractionPoint } from "../characters/InteractionPoint"
import type { ExclusionZone } from "../utils/MathUtils"
import { WaterSurface } from "../effects/WaterSurface"
import { BUILDING, DECOR } from "../assets/AssetManifest"

export interface PoolResortResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
  pondObstacle: { x: number; z: number; radius: number }
  waterSurface: WaterSurface
}

// ─── Pool / deck dimensions ─────────────────────────────────────────────
const POOL_WIDTH = 6
const POOL_DEPTH = 6
const DECK_OUTER = 7.5          // deck extends to ±7.5m (half-width)
const DECK_TOP_Y = 0.18         // top of deck, just above water surface (0.15)
const COPING_Y = 0.22           // thin white tile ring above the deck edge

// ─── Material colors (RGB, 0-1 linear space) ────────────────────────────
const SANDSTONE: [number, number, number] = [0.92, 0.84, 0.66]
const COPING_WHITE: [number, number, number] = [0.96, 0.94, 0.88]
const BOARD_WHITE: [number, number, number] = [0.93, 0.93, 0.90]
const METAL_SILVER: [number, number, number] = [0.82, 0.85, 0.88]
const UMBRELLA_COLORS: ReadonlyArray<[number, number, number]> = [
  [0.85, 0.22, 0.18],  // red over west pair
  [0.25, 0.55, 0.85],  // blue over east pair
  [0.95, 0.75, 0.20],  // yellow over north pair
]
const FLOAT_COLORS: ReadonlyArray<[number, number, number]> = [
  [0.95, 0.35, 0.45],  // coral pink
  [0.25, 0.75, 0.85],  // cyan
]
const TOWEL_COLORS: ReadonlyArray<[number, number, number]> = [
  [0.95, 0.95, 0.88],  // cream
  [0.85, 0.30, 0.35],  // coral
  [0.35, 0.55, 0.85],  // blue
  [0.95, 0.80, 0.25],  // yellow
  [0.40, 0.75, 0.55],  // teal
  [0.85, 0.55, 0.35],  // peach
]

// ─── Placement tables (all in root-local coords) ────────────────────────

/** Lounger positions — MUST stay in sync with BreakSeatGenerator's pool_resort
 *  slots (multiplayer/src/sim/BreakSeatGenerator.ts) or seat-index routing
 *  between server and client will desync. */
const CHAIR_POSITIONS: ReadonlyArray<{ lx: number; lz: number; yaw: number }> = [
  { lx: -5.0, lz: -1.5, yaw: 90 },
  { lx: -5.0, lz: 2.5,  yaw: 90 },
  { lx: 5.0,  lz: -1.5, yaw: -90 },
  { lx: 5.0,  lz: 2.5,  yaw: -90 },
  { lx: -2.5, lz: 5.0,  yaw: 180 },
  { lx: 2.5,  lz: 5.0,  yaw: 180 },
]

/** Umbrella positions — one per lounger pair, pushed behind the chairs so the
 *  pole doesn't clip into the sitter. Length must equal UMBRELLA_COLORS. */
const UMBRELLA_SLOTS: ReadonlyArray<{ lx: number; lz: number }> = [
  { lx: -5.9, lz: 0.5 },
  { lx:  5.9, lz: 0.5 },
  { lx:  0.0, lz: 5.9 },
]

/** Drifting pool-ring floats on the water surface. */
const FLOAT_SLOTS: ReadonlyArray<{ x: number; z: number; rot: number }> = [
  { x: -1.4, z:  1.2, rot: 15 },
  { x:  1.6, z: -0.8, rot: -30 },
]

/** Small side tables between lounger pairs (uses Kenney sideTable GLB). */
const SIDE_TABLE_SLOTS: ReadonlyArray<{ x: number; z: number }> = [
  { x: -4.2, z: 0.5 },   // between west pair
  { x:  4.2, z: 0.5 },   // between east pair
  { x:  0.0, z: 4.2 },   // between north pair
]

/** Flower pots flanking the entrance path (+Z side of the deck). */
const POTTED_PLANT_SLOTS: ReadonlyArray<{ x: number; z: number }> = [
  { x: -1.6, z: 7.2 },
  { x:  1.6, z: 7.2 },
]

/** Decor bushes on grass behind the diving board (-Z, outside deck). */
const BUSH_SLOTS: ReadonlyArray<{ x: number; z: number }> = [
  { x: -5.5, z: -7.8 },
  { x:  5.5, z: -7.8 },
]

export class PoolResortBuilder {
  private factory: BuildingFactory
  private materials: MaterialFactory | null

  constructor(factory: BuildingFactory, _loader: AssetLoader) {
    this.factory = factory
    this.materials = factory.materialFactory
  }

  async build(
    app: Application,
    x: number,
    z: number,
  ): Promise<PoolResortResult> {
    const root = new pc.Entity("PoolResort")
    root.setPosition(x, 0, z)

    const seats: InteractionPoint[] = []

    // ─── Sandstone deck (picture-frame around the pool) ───
    this.buildDeck(root)
    this.buildCoping(root)

    // ─── Procedural water body ───
    const waterSurface = new WaterSurface()
    waterSurface.build(app, this.materials!, {
      x, z,
      width: POOL_WIDTH,
      depth: POOL_DEPTH,
    })

    // ─── Pool features: diving board, ladder, floats ───
    this.buildDivingBoard(root)
    this.buildPoolLadder(root)
    this.buildPoolFloats(root)

    // ─── Loungers + interaction seats (keyed by CHAIR_POSITIONS) ───
    let seatIndex = 0
    for (const pos of CHAIR_POSITIONS) {
      if (!this.materials) continue

      const chair = buildBeachChair(this.materials)
      chair.setLocalPosition(pos.lx, DECK_TOP_Y, pos.lz)
      chair.setLocalEulerAngles(0, pos.yaw, 0)
      root.addChild(chair)
      this.addTowel(chair, seatIndex)

      // Chair sits on the deck, so world seat Y = DECK_TOP_Y + SEAT_HEIGHT.
      seats.push(BuildingFactory.createInteractionSeat(
        'pool_resort', seatIndex++,
        x + pos.lx, z + pos.lz,
        pos.yaw, 'poolChair', 'sit', 0, DECK_TOP_Y + SEAT_HEIGHT,
      ))
    }

    // ─── Shade + tropical accents ───
    this.buildUmbrellas(root)
    await this.buildSideTables(root)
    await this.buildPottedPlants(root)

    app.root.addChild(root)

    return {
      entity: root,
      exclusionZone: { x, z, radius: 14 },
      seats,
      pondObstacle: { x, z, radius: POOL_WIDTH / 2 + 0.5 },
      waterSurface,
    }
  }

  // ───────────────────────────────────────────────────────────────────────
  // Deck & coping
  // ───────────────────────────────────────────────────────────────────────

  /** Four sandstone slabs forming a picture frame around the pool. The
   *  middle (6×6) stays open so the water surface is the only thing the
   *  camera sees inside the pool footprint. */
  private buildDeck(parent: pc.Entity): void {
    if (!this.materials) return
    const mat = this.materials.getColor('pool_deck', ...SANDSTONE, {
      metalness: 0,
      gloss: 0.15,
    })

    const hp = POOL_WIDTH / 2         // pool half-width = 3
    const hd = POOL_DEPTH / 2
    const outer = DECK_OUTER          // 7.5
    const thick = DECK_TOP_Y           // 0.18 (box centered at thick/2)

    const slabs: Array<{ cx: number; cz: number; sx: number; sz: number }> = [
      // North slab (beyond +z pool edge) — spans full outer width
      { cx: 0, cz: (outer + hd) / 2, sx: outer * 2, sz: outer - hd },
      // South slab (beyond -z pool edge)
      { cx: 0, cz: -(outer + hd) / 2, sx: outer * 2, sz: outer - hd },
      // East slab (between ±z pool edges)
      { cx: (outer + hp) / 2, cz: 0, sx: outer - hp, sz: POOL_DEPTH },
      // West slab
      { cx: -(outer + hp) / 2, cz: 0, sx: outer - hp, sz: POOL_DEPTH },
    ]

    for (const s of slabs) {
      const slab = new pc.Entity('DeckSlab')
      slab.addComponent('render', { type: 'box' })
      slab.setLocalScale(s.sx, thick, s.sz)
      slab.setLocalPosition(s.cx, thick / 2, s.cz)
      slab.render!.meshInstances[0].material = mat
      parent.addChild(slab)
    }
  }

  /** Thin white tile ring just inside the deck edge, at the pool lip. Reads
   *  as the classic wet-edge coping seen around resort pools. */
  private buildCoping(parent: pc.Entity): void {
    if (!this.materials) return
    const mat = this.materials.getColor('pool_coping', ...COPING_WHITE, {
      metalness: 0,
      gloss: 0.5,
    })

    const hp = POOL_WIDTH / 2
    const hd = POOL_DEPTH / 2
    const width = 0.35                 // radial thickness of the tile ring
    const height = 0.08                // raised 8cm above the deck
    const y = COPING_Y                  // top at 0.22 + height/2

    const edges: Array<{ cx: number; cz: number; sx: number; sz: number }> = [
      { cx: 0, cz: hd + width / 2, sx: POOL_WIDTH + width * 2, sz: width },
      { cx: 0, cz: -hd - width / 2, sx: POOL_WIDTH + width * 2, sz: width },
      { cx: hp + width / 2, cz: 0, sx: width, sz: POOL_DEPTH },
      { cx: -hp - width / 2, cz: 0, sx: width, sz: POOL_DEPTH },
    ]

    for (const e of edges) {
      const tile = new pc.Entity('Coping')
      tile.addComponent('render', { type: 'box' })
      tile.setLocalScale(e.sx, height, e.sz)
      tile.setLocalPosition(e.cx, y, e.cz)
      tile.render!.meshInstances[0].material = mat
      parent.addChild(tile)
    }
  }

  // ───────────────────────────────────────────────────────────────────────
  // Pool features
  // ───────────────────────────────────────────────────────────────────────

  /** Cantilevered diving board at the -z pool edge. Two short supports hold
   *  a fiberglass-white plank that extends ~1.5m over the water. */
  private buildDivingBoard(parent: pc.Entity): void {
    if (!this.materials) return
    const boardMat = this.materials.getColor('pool_board', ...BOARD_WHITE, {
      metalness: 0,
      gloss: 0.45,
    })
    const metalMat = this.materials.getColor('pool_metal', ...METAL_SILVER, {
      metalness: 0.7,
      gloss: 0.6,
    })

    const baseZ = -POOL_DEPTH / 2 - 0.6   // behind the pool edge on the deck
    const boardY = COPING_Y + 0.18         // above coping

    // Two short metal stanchions
    for (const dx of [-0.25, 0.25]) {
      const stand = new pc.Entity('BoardStand')
      stand.addComponent('render', { type: 'box' })
      stand.setLocalScale(0.08, 0.35, 0.08)
      stand.setLocalPosition(dx, COPING_Y + 0.175, baseZ)
      stand.render!.meshInstances[0].material = metalMat
      parent.addChild(stand)
    }

    // Plank extends from stands (z = baseZ) out over the water (to z ≈ -1.5)
    const board = new pc.Entity('DivingBoard')
    board.addComponent('render', { type: 'box' })
    board.setLocalScale(0.55, 0.06, 2.4)
    board.setLocalPosition(0, boardY, baseZ + 1.2)
    board.render!.meshInstances[0].material = boardMat
    parent.addChild(board)
  }

  /** Chrome ladder at the +x pool wall — two vertical rails descend into the
   *  water, three rungs between. */
  private buildPoolLadder(parent: pc.Entity): void {
    if (!this.materials) return
    const mat = this.materials.getColor('pool_ladder', ...METAL_SILVER, {
      metalness: 0.85,
      gloss: 0.7,
    })

    const wallX = POOL_WIDTH / 2 - 0.02    // just inside the pool wall
    const z = -1.0
    const railTop = COPING_Y + 0.45
    const railBottom = -1.0                  // dips into the water
    const railHeight = railTop - railBottom
    const railSpacing = 0.35

    for (const dz of [-railSpacing / 2, railSpacing / 2]) {
      const rail = new pc.Entity('LadderRail')
      rail.addComponent('render', { type: 'cylinder' })
      rail.setLocalScale(0.045, railHeight, 0.045)
      rail.setLocalPosition(wallX, (railTop + railBottom) / 2, z + dz)
      rail.render!.meshInstances[0].material = mat
      parent.addChild(rail)
    }

    // Rungs
    for (let i = 0; i < 3; i++) {
      const rung = new pc.Entity('LadderRung')
      rung.addComponent('render', { type: 'cylinder' })
      rung.setLocalScale(0.035, railSpacing, 0.035)
      rung.setLocalPosition(wallX, railTop - 0.25 - i * 0.28, z)
      rung.setLocalEulerAngles(90, 0, 0)
      rung.render!.meshInstances[0].material = mat
      parent.addChild(rung)
    }

    // Curved handhold cap at the top of each rail (small sphere)
    for (const dz of [-railSpacing / 2, railSpacing / 2]) {
      const cap = new pc.Entity('LadderCap')
      cap.addComponent('render', { type: 'sphere' })
      cap.setLocalScale(0.09, 0.09, 0.09)
      cap.setLocalPosition(wallX, railTop, z + dz)
      cap.render!.meshInstances[0].material = mat
      parent.addChild(cap)
    }
  }

  /** Two pool-ring floats drifting on the water surface — pure visual sugar
   *  but it's the detail that sells the "someone actually uses this pool"
   *  feel in the overhead view. */
  private buildPoolFloats(parent: pc.Entity): void {
    if (!this.materials) return

    FLOAT_SLOTS.forEach((pos, i) => {
      const color = FLOAT_COLORS[i % FLOAT_COLORS.length]!
      const mat = this.materials!.getColor(`pool_float_${i}`, ...color, {
        metalness: 0,
        gloss: 0.4,
      })

      // Stylised float: flat torus-like disc made of a squashed cylinder
      // (outer) with a smaller darker cylinder on top acting as the hole
      // silhouette. Sits just above the water surface.
      const outer = new pc.Entity('FloatOuter')
      outer.addComponent('render', { type: 'cylinder' })
      outer.setLocalScale(0.7, 0.12, 0.7)
      outer.setLocalPosition(pos.x, 0.22, pos.z)
      outer.setLocalEulerAngles(0, pos.rot, 0)
      outer.render!.meshInstances[0].material = mat
      parent.addChild(outer)

      // Hole (dark water tint) — sits flush with float top so the hole reads
      // as transparency from straight-down camera angles.
      const holeMat = this.materials!.getColor('pool_float_hole', 0.08, 0.25, 0.45, {
        metalness: 0,
        gloss: 0.2,
      })
      const hole = new pc.Entity('FloatHole')
      hole.addComponent('render', { type: 'cylinder' })
      hole.setLocalScale(0.38, 0.13, 0.38)
      hole.setLocalPosition(pos.x, 0.22, pos.z)
      hole.render!.meshInstances[0].material = holeMat
      parent.addChild(hole)
    })
  }

  // ───────────────────────────────────────────────────────────────────────
  // Tropical accents
  // ───────────────────────────────────────────────────────────────────────

  /** Umbrellas over each lounger pair. Delegates to BuildingFactory so the
   *  silhouette matches the coffee/cafeteria umbrellas, but passes per-slot
   *  canopy color + cache key so each umbrella gets its own material. */
  private buildUmbrellas(parent: pc.Entity): void {
    for (let i = 0; i < UMBRELLA_SLOTS.length; i++) {
      const slot = UMBRELLA_SLOTS[i]!
      const color = UMBRELLA_COLORS[i % UMBRELLA_COLORS.length]!
      this.factory.createUmbrella(
        parent, slot.lx, slot.lz,
        DECK_TOP_Y,        // sit on the deck, not the grass
        2.2, 0.95,          // taller + wider than cafeteria umbrellas
        color, `pool_umbrella_${i}`,
      )
    }
  }

  /** Small side tables between each lounger pair. Uses the Kenney sideTable
   *  GLB so the style matches the cafeteria pickup counter. */
  private async buildSideTables(parent: pc.Entity): Promise<void> {
    for (const s of SIDE_TABLE_SLOTS) {
      await this.factory.placeFurnitureCentered(parent, BUILDING.sideTable, s.x, DECK_TOP_Y, s.z)
    }
  }

  /** Flower pots flanking the +Z entrance, plus round bushes on the grass
   *  behind the diving board. Mirrors the cafeteria's entrance-planting
   *  pattern. */
  private async buildPottedPlants(parent: pc.Entity): Promise<void> {
    for (const p of POTTED_PLANT_SLOTS) {
      await this.factory.placeFurniture(parent, BUILDING.pottedPlant, p.x, DECK_TOP_Y, p.z)
    }
    for (const b of BUSH_SLOTS) {
      await this.factory.placeFurniture(parent, DECOR.bushRound, b.x, 0, b.z)
    }
  }

  /** Small colored towel draped on a lounger seat. Cosmetic — adds color
   *  variety from overhead so the chair fabric isn't the only accent. */
  private addTowel(chair: pc.Entity, index: number): void {
    if (!this.materials) return
    const color = TOWEL_COLORS[index % TOWEL_COLORS.length]!
    const mat = this.materials.getColor(`pool_towel_${index}`, ...color, {
      metalness: 0,
      gloss: 0.05,
    })

    const towel = new pc.Entity('Towel')
    towel.addComponent('render', { type: 'box' })
    towel.setLocalScale(0.42, 0.02, 0.5)
    towel.setLocalPosition(0, SEAT_HEIGHT + 0.02, -0.1)
    towel.render!.meshInstances[0].material = mat
    chair.addChild(towel)
  }
}
