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
  umbrellaChairs: `${GARDEN}/umbrella_chairs.glb`,
  deckChair: `${GARDEN}/deck_chair.glb`,
  lilyLarge: `${GARDEN}/lily_large.glb`,
  lilySmall: `${GARDEN}/lily_small.glb`,
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
