// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CoffeeBarLayout — data-driven furniture placement for the interior.
 *
 * Mirrors the pattern used by the house interior (`housetest/SceneConfig.ts`):
 * every item is a row in an array, the scene builder iterates once and places
 * each one. No imperative spaghetti in the scene class.
 *
 * Extensions over the house config:
 *   - `fit`: optional longest-axis target in metres. Items without `fit`
 *            render at native scale (Kenney assets). Items with `fit` use
 *            the world-AABB auto-scaler, needed for the Coffeehouse Lounge
 *            Pack whose GLBs bake inconsistent node transforms.
 *   - `stackOn`: y-position is taken from the top surface of the most
 *                recently-placed item with that asset path.
 *
 * Positions are tuned for a 5×5m room with the door at front-centre (z=5)
 * and the bar counter along the back wall (z=0.5).
 */
import { CAFE } from '../assets/AssetManifest'
import { COFFEE_MACHINE_POS } from './SceneConfig'

/** Named longest-axis targets. Keep the list small — every size should pay rent. */
export const S = {
  PROP: 0.18,       // mug, book stack, cushion, donut, analog clock
  STOOL: 0.32,      // bar stool — must sit comfortably under the coffee table
  SMALL: 0.45,      // coffee machine, cash register, pastry display, plant
  MEDIUM: 0.8,      // coffee table, coat rack
  LARGE: 1.6,       // rug length
} as const

/**
 * Back-wall counter — two-tier wooden structure, built from box primitives:
 *
 *   ┌──────── BACK STEP ────────┐   y = backStepY  (barista-side shelf for
 *   │  (raised, for equipment)  │                   the espresso machine)
 *   ├───────────────────────────┤   y = topY       (main customer counter)
 *   │      MAIN COUNTER         │
 *   └───────────────────────────┘   y = 0
 *           ↑ customer-facing edge
 *
 * The scene class reads these dims to build both tiers, and the layout uses
 * `topY` / `backStepY` as the `y` of every counter prop.
 */
export const COUNTER = {
  /** Spans roughly the right two-thirds of the back wall — left third is
   *  reserved for the wall-mounted menu board, which would otherwise be
   *  occluded by the counter front. */
  width: 2.65,
  depth: 0.6,
  /** Main customer-facing counter top. Shorter than real-world so the menu
   *  board on the back wall stays readable above it. */
  topY: 0.5,
  /** Back-step top — a raised shelf along the wall side of the counter for
   *  the espresso machine / equipment, matching the two-tier reference. */
  backStepY: 0.68,
  /** Z-depth of the raised back step (runs along the wall side). */
  backStepDepth: 0.22,
  /** Counter's centre X/Z in world coordinates. Right edge held at x=4.5,
   *  left edge at x≈1.85 to clear the menu (centred at x=1.2, w=1.1). */
  centreX: 3.175,
  centreZ: 0.4,
} as const

/** World Z of the back-step centre — cached so layout rows can reference it. */
export const COUNTER_BACK_Z =
  COUNTER.centreZ - COUNTER.depth / 2 + COUNTER.backStepDepth / 2
/** World Z of the front (main) counter-top centre, in front of the back step. */
export const COUNTER_FRONT_Z =
  COUNTER.centreZ + COUNTER.depth / 2 - (COUNTER.depth - COUNTER.backStepDepth) / 2

export interface CafeItem {
  /** GLB path from CAFE — pack assets pass through the auto-scaler. */
  asset: string
  x: number
  z: number
  /** Floor level unless `stackOn` is set. */
  y?: number
  /** Euler Y rotation in degrees. */
  rotation?: number
  /** Target longest-axis size in metres. */
  fit?: number
  /**
   * If set, this item's y becomes the top surface height of the most recently
   * placed item with the given asset path. Use for mugs on tables, cushions
   * on couches, books on side tables, etc.
   */
  stackOn?: string
}

// Table X positions — two symmetric clusters at mid-room.
const TABLE_Z = 2.3
const TABLE_LEFT_X = 1.6
const TABLE_RIGHT_X = 3.4
const STOOL_OFFSET = 0.55

// Counter props face -Z (toward the customer walking in through the door).
const COUNTER_PROP_YAW = 180

/** The full interior layout. Order matters: `stackOn` reads the most recently placed. */
export const COFFEE_BAR_LAYOUT: ReadonlyArray<CafeItem> = [
  // ─── Counter equipment — clustered on the right so the menu on the wall
  // above the left / centre of the counter reads clearly without occlusion.
  // Pastry case on the raised back step (glass dome shows from either side),
  // machine + register sit on the main tier facing the customer.
  { asset: CAFE.fancyDonuts,   x: 3.8,                   y: COUNTER.backStepY, z: COUNTER_BACK_Z,  fit: S.SMALL, rotation: COUNTER_PROP_YAW },
  { asset: CAFE.coffeeMachine, x: COFFEE_MACHINE_POS.x,  y: COUNTER.topY,      z: COUNTER_FRONT_Z, fit: S.SMALL, rotation: COUNTER_PROP_YAW },

  // ─── Seating cluster A (left) ─────────────────────────────────────────────
  // Stools sized below table height (S.STOOL=0.32 vs S.MEDIUM=0.8 for the table)
  // so customers can clearly "sit at" the table rather than tower over it.
  { asset: CAFE.coffeeTable, x: TABLE_LEFT_X, z: TABLE_Z,                   fit: S.MEDIUM },
  { asset: CAFE.barStool,    x: TABLE_LEFT_X, z: TABLE_Z - STOOL_OFFSET,    fit: S.STOOL, rotation: 180 },
  { asset: CAFE.barStool,    x: TABLE_LEFT_X, z: TABLE_Z + STOOL_OFFSET,    fit: S.STOOL },

  // ─── Seating cluster B (right) ────────────────────────────────────────────
  { asset: CAFE.coffeeTable, x: TABLE_RIGHT_X, z: TABLE_Z,                  fit: S.MEDIUM },
  { asset: CAFE.barStool,    x: TABLE_RIGHT_X, z: TABLE_Z - STOOL_OFFSET,   fit: S.STOOL, rotation: 180 },
  { asset: CAFE.barStool,    x: TABLE_RIGHT_X, z: TABLE_Z + STOOL_OFFSET,   fit: S.STOOL },

  // ─── Rug under both tables ────────────────────────────────────────────────
  { asset: CAFE.rug, x: 2.5, z: TABLE_Z, fit: S.LARGE },

  // ─── Front decor — plants only. Couch / sideTable / coatRack removed:
  //   - Couch out of scale
  //   - sideTable is a wall-mounted shelf GLB and floated in mid-air
  //   - coatRack read as a stray triangular wood shape in the corner
  { asset: CAFE.houseplant,  x: 4.5, z: 4.3, fit: S.SMALL },
  { asset: CAFE.houseplant2, x: 0.5, z: 3.5, fit: S.SMALL },

]
