/**
 * SceneConfig — data-driven layout for the interior room.
 *
 * All furniture positions, rotations, interaction triggers, and collision
 * boxes live here as typed config arrays. InteriorScene.ts reads these and
 * runs generic builder loops — no magic numbers in the builder code.
 *
 * Coordinate system:
 *   Back wall  Z ≈ 0    Front wall Z ≈ 4
 *   Left wall  X ≈ 0    Right wall X ≈ 4
 *
 * Furniture placement notes:
 *   stackOn: 'assetKey'  →  y = height of the last-placed item with that asset key
 *   y (default 0)        →  floor level; set to 0.01 for rugs etc.
 */
import type { CollisionBox } from './CollisionSystem'

// ─── Action types ─────────────────────────────────────────────────────────────

export type ActionType = 'sit' | 'sleep' | 'use'

export interface SeatConfig {
  x: number
  z: number
  yaw: number  // euler Y facing direction for player
  y?: number   // seat surface height (default 0)
}

// ─── Furniture config ─────────────────────────────────────────────────────────

export interface FurnitureDef {
  /** BUILDING object key, e.g. 'bedSingle' */
  asset: string
  x: number
  /** Floor level unless stackOn is set. Use 0.01 for rugs. */
  y?: number
  z: number
  /** Euler Y rotation in degrees (default 0). */
  rotation?: number
  /** Uniform scale (default 1.0). KayKit furniture needs ~0.5. */
  scale?: number
  /**
   * If set, this item's y is computed from the height of the last entity
   * placed with the given asset key. Use for lamps-on-tables, TVs-on-cabinets, etc.
   */
  stackOn?: string
}

// ─── Interactable config ──────────────────────────────────────────────────────

/** All valid interactable IDs — typed so string comparisons get compile-time safety. */
export type InteractableId = 'tv' | 'laptop' | 'bed'
  | 'couch' | 'chair' | 'armchair' | 'dining'
  | 'pool_chair_0' | 'pool_chair_1' | 'pool_chair_2'
  | 'pool_chair_3' | 'pool_chair_4' | 'pool_chair_5'

export interface InteractableDef {
  id: InteractableId
  /** World-space position used for proximity trigger. */
  pos: { x: number; z: number }
  prompt: string
  info: string
  action: ActionType
  /** Required for 'sit' and 'sleep' actions. */
  seat?: SeatConfig
  /** Proximity radius in world units (default 1.3). */
  radius?: number
}

// ─── Interior layout ──────────────────────────────────────────────────────────

/** Non-interactable decorative furniture placed in the room. */
export const INTERIOR_FURNITURE: FurnitureDef[] = [
  // ── Bed area — back-left wall ────────────────────────────────────────────
  { asset: 'bedSingle',      x: 1.0,  z: 0.3 },
  { asset: 'sideTable',      x: 1.75, z: 0.3 },
  { asset: 'lampRoundTable', x: 1.75, z: 0.3, stackOn: 'sideTable' },

  // ── TV area — right wall, near door (front-right area) ──────────────────
  // rotation=270° → screen faces -X (into room). Chair to the left (smaller X)
  // faces +X (yaw=90°) toward TV. Same Z gives a clean sightline.
  { asset: 'cabinetTelevision', x: 3.6, z: 3.0, rotation: 270 },
  { asset: 'televisionModern',  x: 3.6, z: 3.0, rotation: 270, stackOn: 'cabinetTelevision' },
  // Chair yaw=90° faces +X → toward TV on right wall. ✓
  { asset: 'loungeChair',       x: 2.2, z: 3.0, rotation: 90 },

  // ── Desk area — back-right corner ────────────────────────────────────────
  { asset: 'desk',      x: 3.3, z: 0.5 },
  // Laptop at same X as desk center so it sits correctly on the surface.
  { asset: 'laptop',    x: 3.3, z: 0.5, stackOn: 'desk' },
  // Chair faces -Z (yaw=180°) → looks toward desk at Z=0.5. ✓
  { asset: 'chairDesk', x: 3.3, z: 0.9, rotation: 180 },

  // ── Decorations ───────────────────────────────────────────────────────────
  { asset: 'rugRound',    x: 2.0, y: 0.01, z: 2.0 },
  { asset: 'plantSmall1', x: 0.5, z: 3.5 },
]

/** Interactable items — each triggers an action when the player presses E nearby. */
export const INTERIOR_INTERACTABLES: InteractableDef[] = [
  {
    id: 'tv',
    pos: { x: 3.6, z: 3.0 },
    prompt: '[E] Watch TV',
    info: 'Watching TV... (WASD to stop)',
    action: 'sit',
    seat: { x: 2.2, z: 3.0, yaw: 90, y: 0.15 },
    radius: 1.5,
  },
  {
    id: 'laptop',
    pos: { x: 3.3, z: 0.5 },
    prompt: '[E] Work',
    info: 'Coding away...',
    action: 'sit',
    seat: { x: 3.15, z: 0.95, yaw: 180, y: 0.15 },
    radius: 1.3,
  },
  {
    id: 'bed',
    pos: { x: 1.0, z: 0.8 },
    prompt: '[E] Sleep',
    info: 'Zzzz... (WASD to wake up)',
    action: 'sleep',
    seat: { x: 1.0, z: 0.9, yaw: 0, y: 0.45 },
    radius: 1.3,
  },
]

/**
 * Shared wall boxes used by both the exterior and interior scenes.
 * Door gap is at X=1.0–2.0 on the front wall — matches the door tile at index=1.
 * Exported so ExteriorScene can import rather than duplicate these values.
 */
export const WALL_COLLISION: CollisionBox[] = [
  { minX: -0.1,  maxX: 4.1,  minZ: -0.15, maxZ: 0.15  },  // back
  { minX: -0.15, maxX: 0.15, minZ: -0.1,  maxZ: 4.1   },  // left
  { minX: 3.85,  maxX: 4.15, minZ: -0.1,  maxZ: 4.1   },  // right
  { minX: -0.1,  maxX: 1.0,  minZ: 3.85,  maxZ: 4.15  },  // front-left panel
  { minX: 2.0,   maxX: 4.1,  minZ: 3.85,  maxZ: 4.15  },  // front-right panel
]

// ─── Tier-specific interior configs ──────────────────────────────────────────

export interface RoomSize { width: number; depth: number; doorIndex: number }

export const ROOM_SIZE_BY_TIER: Record<number, RoomSize> = {
  0: { width: 4, depth: 4, doorIndex: 1 },
  1: { width: 3, depth: 3, doorIndex: 1 },
  2: { width: 4, depth: 4, doorIndex: 1 },
  3: { width: 5, depth: 5, doorIndex: 2 },
}

/** Tier 1 — Hut: cozy minimal KayKit room (3×3) */
const KS = 0.3   // KayKit furniture scale (models are ~3x Kenney size)
const KSM = 0.2  // smaller items (lamps, decor)
export const INTERIOR_FURNITURE_TIER_1: FurnitureDef[] = [
  // Bed — back-left against wall
  { asset: 'kaykit_bedSingle',  x: 0.5,  z: 0.3,  scale: KS },
  // Side table + lamp — tight next to bed
  { asset: 'kaykit_tableSmall', x: 1.1,  z: 0.3,  scale: KSM },
  { asset: 'kaykit_lampTable',  x: 1.1,  z: 0.3,  stackOn: 'kaykit_tableSmall', scale: KSM },
  // Desk + laptop + chair — right wall, work area (use Kenney desk+laptop, they align)
  { asset: 'desk',              x: 2.3, z: 0.4, scale: 0.8 },
  { asset: 'laptop',            x: 2.3, z: 0.4, stackOn: 'desk', scale: 0.8 },
  { asset: 'kaykit_chair',      x: 2.3, z: 1.0, rotation: 180, scale: KS },
  // Cactus — front-left corner
  { asset: 'kaykit_cactus',     x: 0.3,  z: 2.4,  scale: KSM },
]

export const INTERIOR_INTERACTABLES_TIER_1: InteractableDef[] = [
  {
    id: 'bed', pos: { x: 0.6, z: 0.5 },
    prompt: '[E] Sleep', info: 'Zzzz...',
    action: 'sleep',
    seat: { x: 0.5, z: 0.5, yaw: 0, y: 0.25 },
    radius: 1.0,
  },
  {
    id: 'laptop', pos: { x: 2.3, z: 0.5 },
    prompt: '[E] Work', info: 'Coding away...',
    action: 'sit',
    seat: { x: 2.3, z: 0.8, yaw: 180 },
    radius: 1.0,
  },
]

export const INTERIOR_COLLISION_TIER_1: CollisionBox[] = [
  { minX: -0.1,  maxX: 3.1,  minZ: -0.15, maxZ: 0.15 },  // back
  { minX: -0.15, maxX: 0.15, minZ: -0.1,  maxZ: 3.1  },  // left
  { minX: 2.85,  maxX: 3.15, minZ: -0.1,  maxZ: 3.1  },  // right
  { minX: -0.1,  maxX: 1.0,  minZ: 2.85,  maxZ: 3.15 },  // front-left
  { minX: 2.0,   maxX: 3.1,  minZ: 2.85,  maxZ: 3.15 },  // front-right
]

/** Tier 2 — Cottage: comfortable KayKit home (4×4) */
export const INTERIOR_FURNITURE_TIER_2: FurnitureDef[] = [
  // Bed area — back-left
  { asset: 'kaykit_bedSingle',    x: 0.6,  z: 0.3, scale: KS },
  { asset: 'kaykit_tableSmall',   x: 1.4,  z: 0.3, scale: KSM },
  { asset: 'kaykit_lampTable',    x: 1.4,  z: 0.3, stackOn: 'kaykit_tableSmall', scale: KSM },
  // Living area — center-right
  { asset: 'kaykit_couchPillows', x: 3.3,  z: 2.5, rotation: 270, scale: KS },
  { asset: 'kaykit_tableMedium',  x: 2.0,  z: 2.5, scale: KS },
  { asset: 'kaykit_chair',        x: 2.0,  z: 1.5, rotation: 180, scale: KS },
  // Reading corner — back-right
  { asset: 'kaykit_bookshelf',    x: 3.5,  z: 0.2, rotation: 270, scale: KS },
  { asset: 'kaykit_books',        x: 2.0,  z: 2.5, stackOn: 'kaykit_tableMedium', scale: KSM },
  // Lighting + decor
  { asset: 'kaykit_lampStanding', x: 0.3,  z: 2.8, scale: KSM },
  { asset: 'kaykit_rugRectangle', x: 2.0,  y: 0.01, z: 2.0, scale: KS },
  { asset: 'kaykit_cactus',       x: 0.3,  z: 3.5, scale: KSM },
]

export const INTERIOR_INTERACTABLES_TIER_2: InteractableDef[] = [
  {
    id: 'bed', pos: { x: 0.8, z: 0.3 },
    prompt: '[E] Sleep', info: 'Zzzz...',
    action: 'sleep',
    seat: { x: 0.8, z: 0.55, yaw: 90 },
  },
  {
    id: 'couch', pos: { x: 3.2, z: 2.5 },
    prompt: '[E] Sit on couch', info: 'Comfortable...',
    action: 'sit',
    seat: { x: 3.2, z: 2.5, yaw: 270 },
    radius: 1.3,
  },
  {
    id: 'chair', pos: { x: 2.0, z: 1.5 },
    prompt: '[E] Sit', info: 'Reading...',
    action: 'sit',
    seat: { x: 2.0, z: 1.5, yaw: 180 },
  },
]

/** Tier 3 — Mansion: luxury KayKit estate (5×5) */
export const INTERIOR_FURNITURE_TIER_3: FurnitureDef[] = [
  // Master bedroom — back-left
  { asset: 'kaykit_bedDouble',    x: 1.0,  z: 0.3, scale: KS },
  { asset: 'kaykit_tableSmall',   x: 0.2,  z: 0.3, scale: KSM },
  { asset: 'kaykit_lampTable',    x: 0.2,  z: 0.3, stackOn: 'kaykit_tableSmall', scale: KSM },
  { asset: 'kaykit_tableSmall',   x: 2.0,  z: 0.3, scale: KSM },
  { asset: 'kaykit_lampTable',    x: 2.0,  z: 0.3, stackOn: 'kaykit_tableSmall', scale: KSM },
  // Living room — right side
  { asset: 'kaykit_couchPillows', x: 4.3,  z: 3.0, rotation: 270, scale: KS },
  { asset: 'kaykit_armchair',     x: 3.2,  z: 4.0, rotation: 0, scale: KS },
  { asset: 'kaykit_tableMedium',  x: 3.2,  z: 2.8, scale: KS },
  // Dining area — front-left
  { asset: 'kaykit_tableMedium',  x: 1.2,  z: 3.5, scale: KS },
  { asset: 'kaykit_chair',        x: 0.5,  z: 3.5, rotation: 90, scale: KS },
  { asset: 'kaykit_chair',        x: 1.9,  z: 3.5, rotation: 270, scale: KS },
  // Study corner — back-right
  { asset: 'kaykit_bookshelf',    x: 4.5,  z: 0.2, rotation: 270, scale: KS },
  { asset: 'kaykit_cabinet',      x: 3.5,  z: 0.2, scale: KS },
  { asset: 'kaykit_books',        x: 3.2,  z: 2.8, stackOn: 'kaykit_tableMedium', scale: KSM },
  // Lighting
  { asset: 'kaykit_lampStanding', x: 0.3,  z: 2.0, scale: KSM },
  { asset: 'kaykit_lampStanding', x: 4.5,  z: 4.5, scale: KSM },
  // Decor
  { asset: 'kaykit_rugRectangle', x: 3.2,  y: 0.01, z: 3.2, scale: KS },
  { asset: 'kaykit_rugOval',      x: 1.0,  y: 0.01, z: 1.5, scale: KS },
  { asset: 'kaykit_cactus',       x: 0.3,  z: 4.5, scale: KSM },
  { asset: 'kaykit_cactus',       x: 4.7,  z: 1.5, scale: KSM },
]

export const INTERIOR_INTERACTABLES_TIER_3: InteractableDef[] = [
  {
    id: 'bed', pos: { x: 1.2, z: 0.3 },
    prompt: '[E] Sleep', info: 'Luxury sleep...',
    action: 'sleep',
    seat: { x: 1.2, z: 0.55, yaw: 90 },
  },
  {
    id: 'couch', pos: { x: 4.2, z: 3.0 },
    prompt: '[E] Relax on couch', info: 'Living the dream...',
    action: 'sit',
    seat: { x: 4.2, z: 3.0, yaw: 270 },
    radius: 1.3,
  },
  {
    id: 'armchair', pos: { x: 3.0, z: 4.0 },
    prompt: '[E] Sit in armchair', info: 'Cozy...',
    action: 'sit',
    seat: { x: 3.0, z: 4.0, yaw: 0 },
  },
  {
    id: 'dining', pos: { x: 0.5, z: 3.5 },
    prompt: '[E] Sit at table', info: 'Dinner time...',
    action: 'sit',
    seat: { x: 0.5, z: 3.5, yaw: 90 },
  },
]

export const INTERIOR_COLLISION_TIER_3: CollisionBox[] = [
  { minX: -0.1,  maxX: 5.1,  minZ: -0.15, maxZ: 0.15 },  // back
  { minX: -0.15, maxX: 0.15, minZ: -0.1,  maxZ: 5.1  },  // left
  { minX: 4.85,  maxX: 5.15, minZ: -0.1,  maxZ: 5.1  },  // right
  { minX: -0.1,  maxX: 2.0,  minZ: 4.85,  maxZ: 5.15 },  // front-left
  { minX: 3.0,   maxX: 5.1,  minZ: 4.85,  maxZ: 5.15 },  // front-right
]

/** Lookup helpers for tier-specific configs */
export function getFurnitureForTier(tier: number): FurnitureDef[] {
  switch (tier) {
    case 1: return INTERIOR_FURNITURE_TIER_1
    case 2: return INTERIOR_FURNITURE_TIER_2
    case 3: return INTERIOR_FURNITURE_TIER_3
    default: return INTERIOR_FURNITURE  // tier 0 = standard
  }
}

export function getInteractablesForTier(tier: number): InteractableDef[] {
  switch (tier) {
    case 1: return INTERIOR_INTERACTABLES_TIER_1
    case 2: return INTERIOR_INTERACTABLES_TIER_2
    case 3: return INTERIOR_INTERACTABLES_TIER_3
    default: return INTERIOR_INTERACTABLES
  }
}

export function getCollisionForTier(tier: number): CollisionBox[] {
  switch (tier) {
    case 0: return INTERIOR_COLLISION  // standard walls + furniture footprints
    case 1: return INTERIOR_COLLISION_TIER_1
    case 3: return INTERIOR_COLLISION_TIER_3
    default: return WALL_COLLISION  // tier 2 uses wall-only collision
  }
}

// ─── Multi-house exterior layout ─────────────────────────────────────────────

export interface ExteriorHouseDef {
  id: string
  x: number       // world X of house origin (lower-left corner in local space)
  z: number       // world Z
  label: string   // member name shown above house
  tier: 0 | 1 | 2 | 3 // 0=standard (old Kenney), 1-3=KayKit upgrades
}

/** 5 houses showing all tiers: standard (old Kenney) + 3 KayKit upgrades. */
export const EXTERIOR_HOUSES: ExteriorHouseDef[] = [
  { id: 'house_a', x: 0,   z: 0,  label: 'Alice (Standard)', tier: 0 },
  { id: 'house_b', x: 7,   z: 0,  label: 'Bob (Hut)',        tier: 1 },
  { id: 'house_c', x: 0,   z: 9,  label: 'Carol (Cottage)',  tier: 2 },
  { id: 'house_d', x: 7,   z: 9,  label: 'Dave (Mansion)',   tier: 3 },
  { id: 'house_e', x: 14,  z: 0,  label: 'Eve (Standard)',   tier: 0 },
]

/** Door center in house-local coordinates (X=1.5 centered in door gap, Z=4.0 front wall). */
export const HOUSE_DOOR_LOCAL = { x: 1.5, z: 4.7 }

/** Exit spawn offset from door (outside the house, clear of sensor). */
export const HOUSE_EXIT_LOCAL = { x: 1.5, z: 6.0 }

// ─── Collision ───────────────────────────────────────────────────────────────

/** AABB collision boxes for walls and solid furniture.
 *  Sittable items (lounge chair, bed) are excluded — they would trap
 *  the player inside the collision box after sitAt()/sleepAt(). */
export const INTERIOR_COLLISION: CollisionBox[] = [
  ...WALL_COLLISION,

  // Furniture footprints
  // Bed excluded — player sleeps inside it; back wall box already blocks going through wall
  { minX: 2.65, maxX: 3.95, minZ: 0.05, maxZ: 0.72 },  // desk only (chair area left open so player can sit)
  { minX: 3.25, maxX: 3.85, minZ: 2.65, maxZ: 3.35 },  // TV cabinet (right wall, near door)
]

// ─── Pool scene ─────────────────────────────────────────────────────────────
// 6 umbrella+chair sets arranged around a central pool area.
// Seats are NOT hardcoded — SeatProber detects the actual chair surface from geometry.

export interface PoolChairDef {
  id: InteractableId
  /** Local X position relative to pool center. */
  x: number
  /** Local Z position relative to pool center. */
  z: number
  /** Yaw in degrees — chair faces this direction toward pool. */
  yaw: number
}

export const POOL_CHAIRS: PoolChairDef[] = [
  // Left side: facing pool (+X → yaw 90)
  { id: 'pool_chair_0', x: -5.0, z: -1.5, yaw: 90 },
  { id: 'pool_chair_1', x: -5.0, z:  2.5, yaw: 90 },
  // Right side: facing pool (-X → yaw -90)
  { id: 'pool_chair_2', x:  5.0, z: -1.5, yaw: -90 },
  { id: 'pool_chair_3', x:  5.0, z:  2.5, yaw: -90 },
  // Far end: facing pool (-Z → yaw 180)
  { id: 'pool_chair_4', x: -2.5, z:  5.0, yaw: 180 },
  { id: 'pool_chair_5', x:  2.5, z:  5.0, yaw: 180 },
]
