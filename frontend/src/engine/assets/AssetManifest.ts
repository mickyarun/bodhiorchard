// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * AssetManifest — Central catalog of all Kenney asset paths + metadata.
 *
 * Maps game concepts (growth stage, health, decoration type) to GLB file paths.
 * All paths are relative to the public root (served by Vite as static assets).
 */
import type { RepoHealth, ThreatSeverity, BUDStatus } from '../types'

// ─── Base Paths ─────────────────────────────────

const GARDEN = 'assets/garden'
const FURNITURE = 'assets/furniture'
const CHARACTERS = 'characters'
/** Coffeehouse Lounge Pack by majesticmaje (CC-BY via Poly.Pizza). See
 *  `public/models/coffeebar/ATTRIBUTION.md` for the full notice. */
const CAFE_PACK = 'models/coffeebar'
/** Single-scene Cafeteria GLB from fab.com (styloo, free under Standard License). */
const CAFETERIA_PACK = 'models/cafeteria'

// ─── Tree GLBs ──────────────────────────────────

type GrowthStage = 'sprout' | 'sapling' | 'medium' | 'mature'

/** Map (growth_stage, health) → GLB path for repo trees. */
const TREE_MAP: Record<GrowthStage, Record<'normal' | 'dormant' | 'wilted', string>> = {
  sprout: {
    normal: `${GARDEN}/tree_simple.glb`,
    dormant: `${GARDEN}/tree_simple.glb`,
    wilted: `${GARDEN}/tree_simple.glb`,
  },
  sapling: {
    normal: `${GARDEN}/tree_thin.glb`,
    dormant: `${GARDEN}/tree_cone.glb`,
    wilted: `${GARDEN}/tree_cone.glb`,
  },
  medium: {
    normal: `${GARDEN}/tree_default.glb`,
    dormant: `${GARDEN}/tree_default_dark.glb`,
    wilted: `${GARDEN}/tree_default_fall.glb`,
  },
  mature: {
    normal: `${GARDEN}/tree_oak.glb`,
    dormant: `${GARDEN}/tree_oak_dark.glb`,
    wilted: `${GARDEN}/tree_oak_fall.glb`,
  },
}

export function getTreeGLB(growth: GrowthStage, health: RepoHealth): string {
  const variant = health === 'dormant' ? 'dormant'
    : health === 'wilted' ? 'wilted'
    : 'normal'
  return TREE_MAP[growth][variant]
}

/** All unique tree GLB paths (for batch preloading). */
export function getAllTreeGLBs(): string[] {
  const set = new Set<string>()
  for (const stage of Object.values(TREE_MAP)) {
    for (const path of Object.values(stage)) {
      set.add(path)
    }
  }
  return [...set]
}

// ─── Decoration GLBs ────────────────────────────

/** Features → flowers (color based on status). */
const FEATURE_FLOWERS: string[] = [
  `${GARDEN}/flower_purpleA.glb`,
  `${GARDEN}/flower_purpleB.glb`,
  `${GARDEN}/flower_purpleC.glb`,
  `${GARDEN}/flower_redA.glb`,
  `${GARDEN}/flower_redB.glb`,
  `${GARDEN}/flower_yellowA.glb`,
  `${GARDEN}/flower_yellowB.glb`,
]

/** BUDs → smaller flower buds. */
const BUD_FLOWERS: string[] = [
  `${GARDEN}/flower_yellowC.glb`,
  `${GARDEN}/flower_redC.glb`,
  `${GARDEN}/flower_purpleC.glb`,
]

export function getFeatureFlowerGLB(index: number): string {
  return FEATURE_FLOWERS[index % FEATURE_FLOWERS.length]
}

export function getBudFlowerGLB(status: BUDStatus): string {
  if (status === 'bud' || status === 'design') return BUD_FLOWERS[0]
  if (status === 'development' || status === 'testing') return BUD_FLOWERS[1]
  return BUD_FLOWERS[2]
}

/** Threats → mushrooms. */
export function getThreatGLB(severity: ThreatSeverity): string {
  return severity === 'critical' || severity === 'high'
    ? `${GARDEN}/mushroom_red.glb`
    : `${GARDEN}/mushroom_tan.glb`
}

export function getAllDecorationGLBs(): string[] {
  return [
    ...FEATURE_FLOWERS,
    ...BUD_FLOWERS,
    `${GARDEN}/mushroom_red.glb`,
    `${GARDEN}/mushroom_tan.glb`,
  ]
}

// ─── Scatter GLBs (Grass, Rocks) ────────────────

export const SCATTER_GRASS: string[] = [
  `${GARDEN}/grass.glb`,
  `${GARDEN}/grass_large.glb`,
  `${GARDEN}/grass_leafs.glb`,
]

export const SCATTER_FLOWERS: string[] = [
  `${GARDEN}/flower_purpleA.glb`,
  `${GARDEN}/flower_redA.glb`,
  `${GARDEN}/flower_yellowA.glb`,
]

export const SCATTER_ROCKS: string[] = [
  `${GARDEN}/rock_smallA.glb`,
  `${GARDEN}/rock_smallB.glb`,
  `${GARDEN}/rock_smallC.glb`,
  `${GARDEN}/rock_largeA.glb`,
  `${GARDEN}/rock_largeB.glb`,
  `${GARDEN}/rock_tallA.glb`,
  `${GARDEN}/rock_tallB.glb`,
  `${GARDEN}/stone_smallA.glb`,
  `${GARDEN}/stone_smallB.glb`,
]

export const SCATTER_PINES: string[] = [
  `${GARDEN}/pine_tree.glb`,
]

export const FOREST_TREES: string[] = [
  `${GARDEN}/pine_tree.glb`,
  `${GARDEN}/tree_round.glb`,
  `${GARDEN}/tree_tall_green.glb`,
  `${GARDEN}/tree_leafy.glb`,
  `${GARDEN}/tree_autumn.glb`,
]

export const SCATTER_BUSHES: string[] = [
  `${GARDEN}/bush_green.glb`,
  `${GARDEN}/bushes_cluster.glb`,
  `${GARDEN}/bush_round.glb`,
]

export const MOUNTAINS: string[] = [
  `${GARDEN}/mountains.glb`,
  `${GARDEN}/mountain.glb`,
  `${GARDEN}/mountain_b.glb`,
]

export const SCATTER_PROPS: string[] = [
  `${GARDEN}/stump_old.glb`,
  `${GARDEN}/stump_round.glb`,
  `${GARDEN}/log.glb`,
  `${GARDEN}/log_stack.glb`,
  `${GARDEN}/plant_bush.glb`,
  `${GARDEN}/plant_bushLarge.glb`,
  `${GARDEN}/plant_bushSmall.glb`,
]

// ─── Building / Furniture GLBs ──────────────────

export const BUILDING = {
  // Structure
  wall: `${FURNITURE}/wall.glb`,
  wallWindow: `${FURNITURE}/wallWindow.glb`,
  wallDoorway: `${FURNITURE}/wallDoorway.glb`,
  floorFull: `${FURNITURE}/floorFull.glb`,
  doorway: `${FURNITURE}/doorway.glb`,
  stairs: `${FURNITURE}/stairs.glb`,

  // Coffee bar
  kitchenBar: `${FURNITURE}/kitchenBar.glb`,
  kitchenBarEnd: `${FURNITURE}/kitchenBarEnd.glb`,
  kitchenCoffeeMachine: `${FURNITURE}/kitchenCoffeeMachine.glb`,
  chair: `${FURNITURE}/chair.glb`,
  chairCushion: `${FURNITURE}/chairCushion.glb`,
  tableRound: `${FURNITURE}/tableRound.glb`,
  tableCoffee: `${FURNITURE}/tableCoffee.glb`,

  // Cafeteria
  bench: `${FURNITURE}/bench.glb`,
  benchCushion: `${FURNITURE}/benchCushion.glb`,
  benchCushionLow: `${FURNITURE}/benchCushionLow.glb`,
  tableCloth: `${FURNITURE}/tableCloth.glb`,
  tableCross: `${FURNITURE}/tableCross.glb`,
  kitchenStove: `${FURNITURE}/kitchenStove.glb`,
  kitchenSink: `${FURNITURE}/kitchenSink.glb`,
  kitchenFridge: `${FURNITURE}/kitchenFridge.glb`,
  kitchenCabinet: `${FURNITURE}/kitchenCabinet.glb`,

  // Housing
  bedSingle: `${FURNITURE}/bedSingle.glb`,
  bedDouble: `${FURNITURE}/bedDouble.glb`,
  loungeChair: `${FURNITURE}/loungeChair.glb`,
  loungeSofa: `${FURNITURE}/loungeSofa.glb`,
  cabinetTelevision: `${FURNITURE}/cabinetTelevision.glb`,
  televisionModern: `${FURNITURE}/televisionModern.glb`,
  lampRoundFloor: `${FURNITURE}/lampRoundFloor.glb`,
  rugRound: `${FURNITURE}/rugRound.glb`,
  desk: `${FURNITURE}/desk.glb`,
  chairDesk: `${FURNITURE}/chairDesk.glb`,
  laptop: `${FURNITURE}/laptop.glb`,
  books: `${FURNITURE}/books.glb`,
  plantSmall1: `${FURNITURE}/plantSmall1.glb`,
  plantSmall2: `${FURNITURE}/plantSmall2.glb`,
  pottedPlant: `${FURNITURE}/pottedPlant.glb`,

  // Pool resort
  loungeChairRelax: `${FURNITURE}/loungeChairRelax.glb`,
  loungeDesignChair: `${FURNITURE}/loungeDesignChair.glb`,

  // Misc
  sideTable: `${FURNITURE}/sideTable.glb`,
  lampRoundTable: `${FURNITURE}/lampRoundTable.glb`,
  table: `${FURNITURE}/table.glb`,
  rugRectangle: `${FURNITURE}/rugRectangle.glb`,

  // KayKit Furniture Bits
  kaykit_bedSingle: `${FURNITURE}/kaykit/bed_single_A.glb`,
  kaykit_bedDouble: `${FURNITURE}/kaykit/bed_double_A.glb`,
  kaykit_chair: `${FURNITURE}/kaykit/chair_A.glb`,
  kaykit_armchair: `${FURNITURE}/kaykit/armchair_pillows.glb`,
  kaykit_couch: `${FURNITURE}/kaykit/couch.glb`,
  kaykit_couchPillows: `${FURNITURE}/kaykit/couch_pillows.glb`,
  kaykit_tableMedium: `${FURNITURE}/kaykit/table_medium.glb`,
  kaykit_tableSmall: `${FURNITURE}/kaykit/table_small.glb`,
  kaykit_lampStanding: `${FURNITURE}/kaykit/lamp_standing.glb`,
  kaykit_lampTable: `${FURNITURE}/kaykit/lamp_table.glb`,
  kaykit_rugRectangle: `${FURNITURE}/kaykit/rug_rectangle_A.glb`,
  kaykit_rugOval: `${FURNITURE}/kaykit/rug_oval_A.glb`,
  kaykit_cabinet: `${FURNITURE}/kaykit/cabinet_medium.glb`,
  kaykit_bookshelf: `${FURNITURE}/kaykit/shelf_B_large_decorated.glb`,
  kaykit_books: `${FURNITURE}/kaykit/book_set.glb`,
  kaykit_cactus: `${FURNITURE}/kaykit/cactus_small_A.glb`,
} as const

// Campfire / pavilion
export const CAMPFIRE = {
  stones: `${GARDEN}/campfire_stones.glb`,
  logs: `${GARDEN}/campfire_logs.glb`,
  /** Sketchfab fireplace with cauldron + stands. Z-up, 100× matrix baked in. */
  fireplace: `${GARDEN}/fireplace.glb`,
} as const

export const PAVILION = {
  fence: `${GARDEN}/fence_simple.glb`,
  pathStone: `${GARDEN}/path_stone.glb`,
} as const

export const ANIMALS = {
  cat:   `${GARDEN}/animal-cat.glb`,
  dog:   `${GARDEN}/animal-dog.glb`,
  bunny: `${GARDEN}/animal-bunny.glb`,
  fox:   `${GARDEN}/animal-fox.glb`,
  deer:  `${GARDEN}/animal-deer.glb`,
} as const

export const POOL = {
  lilyLarge: `${GARDEN}/lily_large.glb`,
  lilySmall: `${GARDEN}/lily_small.glb`,
} as const

// ─── Café pack GLBs (Coffeehouse Lounge Pack by majesticmaje, CC-BY) ──

/**
 * Individual café props from the Coffeehouse Lounge Pack. Subset of the
 * 81-model pack — only the ones we actually place in the coffee bar.
 * Full inventory lives in `public/models/coffeebar/`.
 */
export const CAFE = {
  // Equipment on / around the bar counter
  coffeeMachine: `${CAFE_PACK}/Coffee_Machine.glb`,
  cashRegister:  `${CAFE_PACK}/Cash_register.glb`,
  coffeePot:     `${CAFE_PACK}/Coffee_Pot.glb`,
  espressoPot:   `${CAFE_PACK}/Espresso_Pot.glb`,
  tripleSink:    `${CAFE_PACK}/Triple_Sink.glb`,
  kitchenCabinetCorner: `${CAFE_PACK}/Kitchen_Cabinet_Corner.glb`,

  // Display / countertop treats
  fancyDonuts:  `${CAFE_PACK}/Fancy_Donuts.glb`,
  donut:        `${CAFE_PACK}/Donut.glb`,
  cupcake:      `${CAFE_PACK}/Cupcake.glb`,
  frappe:       `${CAFE_PACK}/Frappe.glb`,
  cup:          `${CAFE_PACK}/Cup.glb`,
  mug:          `${CAFE_PACK}/Mug.glb`,
  mugs:         `${CAFE_PACK}/Mugs.glb`,
  coffeeCup:    `${CAFE_PACK}/Coffee_cup.glb`,
  coffeeBean:   `${CAFE_PACK}/Coffee_bean.glb`,
  fruitBowl:    `${CAFE_PACK}/Fruit_Bowl.glb`,
  heartChocolates: `${CAFE_PACK}/Heart_Chocolates.glb`,

  // Seating
  coffeeTable: `${CAFE_PACK}/Coffee_Table.glb`,
  table:       `${CAFE_PACK}/Table.glb`,
  sideTable:   `${CAFE_PACK}/Side_table.glb`,
  barStool:    `${CAFE_PACK}/Bar_Stool.glb`,
  barStoolAlt: `${CAFE_PACK}/Barstool.glb`,
  couchSmall:  `${CAFE_PACK}/Couch_Small.glb`,
  couchMedium: `${CAFE_PACK}/Couch_Medium.glb`,
  cushions:    `${CAFE_PACK}/Cushions.glb`,

  // Decor
  coffeeSign:   `${CAFE_PACK}/Coffee_sign.glb`,
  coatRack:     `${CAFE_PACK}/Coat_Rack.glb`,
  ceilingLight: `${CAFE_PACK}/Ceiling_Light.glb`,
  analogClock:  `${CAFE_PACK}/Analog_clock.glb`,
  calendar:     `${CAFE_PACK}/Calendar.glb`,
  bookStack:    `${CAFE_PACK}/Book_Stack.glb`,
  houseplant:   `${CAFE_PACK}/Houseplant.glb`,
  houseplant2:  `${CAFE_PACK}/Houseplant-bfLOqIV5uP.glb`,
  houseplant3:  `${CAFE_PACK}/Houseplant-IBLX2Jz90O.glb`,
  rug:          `${CAFE_PACK}/Rug.glb`,
  roundRug:     `${CAFE_PACK}/Round_Rug.glb`,
  bins:         `${CAFE_PACK}/Bins.glb`,
} as const

// ─── Cafeteria GLB (single-scene interior) ──────

/**
 * Cafeteria interior — one GLB contains the entire dining hall
 * (walls, tables, chairs, vending machines, food display).
 */
export const CAFETERIA = {
  room: `${CAFETERIA_PACK}/cafeteria.glb`,
} as const

// ─── Character GLBs ─────────────────────────────

/** Legacy Kenney Blocky Characters (18 variants, moved to legacy/ subfolder). */
const LEGACY_CHARACTERS = `${CHARACTERS}/legacy`

const CHARACTER_MODELS = [
  'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i',
  'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r',
] as const

export function getCharacterGLB(variant: string): string {
  return `${LEGACY_CHARACTERS}/character-${variant}.glb`
}

export function getAllCharacterGLBs(): string[] {
  return CHARACTER_MODELS.map(v => getCharacterGLB(v))
}

export const CHARACTER_COUNT = CHARACTER_MODELS.length

// ─── Texture Paths ──────────────────────────────

export const TEXTURES = {
  grass: `${GARDEN}/grass.jpg`,
  dirtColor: `${GARDEN}/dirt_color.jpg`,
  dirtNormal: `${GARDEN}/dirt_normal.jpg`,
} as const

// ─── Batch Preload Helpers ──────────────────────

/** All GLBs needed for the environment (grass, flowers, rocks, pines, bushes, props). */
export function getEnvironmentGLBs(): string[] {
  return [
    ...SCATTER_GRASS,
    ...SCATTER_FLOWERS,
    ...SCATTER_ROCKS,
    ...SCATTER_PINES,
    ...FOREST_TREES,
    ...SCATTER_BUSHES,
    ...MOUNTAINS,
    ...SCATTER_PROPS,
  ]
}

/** All GLBs needed for buildings. */
export function getBuildingGLBs(): string[] {
  return Object.values(BUILDING)
}

/** All GLBs from the Coffeehouse Lounge Pack used in the café interior. */
export function getCafeGLBs(): string[] {
  return Object.values(CAFE)
}

/** Path stone GLB for connecting zones. */
export const PATH = {
  stone: `${GARDEN}/path_stone.glb`,
} as const

/** Agent robot character GLB. */
export const AGENT_ROBOT = 'assets/agents/robot.glb'

/** Agent spaceship transport GLB. */
export const AGENT_SPACESHIP = 'assets/agents/spaceship.glb'

/** All campfire + pavilion + pool + path GLBs. */
export function getMiscGLBs(): string[] {
  return [
    ...Object.values(CAMPFIRE),
    ...Object.values(PAVILION),
    ...Object.values(POOL),
    ...Object.values(PATH),
    'assets/garden/animal-parrot.glb',
    ...Object.values(ANIMALS),
  ]
}
