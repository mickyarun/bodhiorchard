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
  /**
   * If set, this item's y is computed from the height of the last entity
   * placed with the given asset key. Use for lamps-on-tables, TVs-on-cabinets, etc.
   */
  stackOn?: string
}

// ─── Interactable config ──────────────────────────────────────────────────────

/** All valid interactable IDs — typed so string comparisons get compile-time safety. */
export type InteractableId = 'tv' | 'laptop' | 'bed'

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
    // Player sits in the lounge chair at (2.2, 3.0), yaw=90° faces +X toward TV.
    seat: { x: 2.2, z: 3.0, yaw: 90 },
    radius: 1.5,
  },
  {
    id: 'laptop',
    pos: { x: 3.3, z: 0.5 },
    prompt: '[E] Check emails',
    info: 'You have 3 unread messages.',
    action: 'sit',
    // z=1.1: bottom edge at 1.1-0.28=0.82 > desk box maxZ(0.72) → outside box ✓
    seat: { x: 3.3, z: 1.1, yaw: 180 },
    radius: 1.3,
  },
  {
    id: 'bed',
    pos: { x: 1.0, z: 0.3 },
    prompt: '[E] Sleep',
    info: 'Zzzz... (WASD to wake up)',
    action: 'sleep',
    // z=0.55: bottom edge at 0.55-0.28=0.27 > back wall box maxZ(0.15) → outside box ✓
    seat: { x: 1.0, z: 0.55, yaw: 90 },
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

// ─── Multi-house exterior layout ─────────────────────────────────────────────

export interface ExteriorHouseDef {
  id: string
  x: number       // world X of house origin (lower-left corner in local space)
  z: number       // world Z
  label: string   // member name shown above house
}

/** 4 houses in a 2×2 grid, 6-unit spacing. Door faces +Z (front wall). */
export const EXTERIOR_HOUSES: ExteriorHouseDef[] = [
  { id: 'house_a', x: 0,  z: 0,  label: 'Alice' },
  { id: 'house_b', x: 6,  z: 0,  label: 'Bob' },
  { id: 'house_c', x: 0,  z: 8,  label: 'Carol' },
  { id: 'house_d', x: 6,  z: 8,  label: 'Dave' },
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
