/**
 * TakeoverPhysicsBuilder — Scene-to-physics translation layer.
 *
 * Single source of truth for converting visual scene elements
 * (houses, buildings, pond, world edge) into Rapier physics colliders.
 *
 * Usage:
 *   const builder = new TakeoverPhysicsBuilder(physics)
 *   builder.registerHouses(memberHouseMap)
 *   builder.registerBuildings(huts)
 *   builder.registerPond(poolObstacle)
 *   builder.registerPerimeter(worldRadius)
 *
 * Design principles:
 *   - Pure translation: no UI, input, or state knowledge
 *   - Deterministic: same input → same physics state
 *   - Rotation-aware: handles 90° building rotations correctly
 */
import type { PhysicsWorld } from '../physics'
import { WALL_HEIGHT, type HouseResult } from '../buildings/HouseBuilder'
import { getHouseTier } from '../buildings/HouseTierConfig'

// ─── Constants ─────────────────────────────────

/** Single source of truth for wall height — shared with visual HouseBuilder. */
const HOUSE_WALL_HEIGHT = WALL_HEIGHT

const HOUSE_DOOR_HALF_W = 0.45   // slightly narrower than 1-unit door gap
const HOUSE_DOOR_HALF_D = 0.05   // thin trigger
const HOUSE_WALL_THICK = 0.15    // half-thickness of wall boxes

/** Door tile index per tier (must match HouseBuilder wall openings). */
const TIER_DOOR_INDEX: Record<number, number> = { 1: 1, 2: 1, 3: 2 }

// ─── Public Types ──────────────────────────────

/** Hut dimensions exported by building results (coffee bar, cafeteria, pavilion). */
export interface HutInfo {
  x: number              // world X of hut root entity
  z: number              // world Z
  yawDeg: number         // hut rotation (degrees, Y axis)
  width: number          // tile count (W direction, local X)
  depth: number          // tile count (D direction, local Z)
  frontDoorIndices: number[]  // tile indices on front wall with door gaps
}

/** Pond obstacle exported by pool builder. */
export interface PondObstacle {
  x: number
  z: number
  radius: number
}

// ─── Builder ───────────────────────────────────

export class TakeoverPhysicsBuilder {
  private physics: PhysicsWorld

  constructor(physics: PhysicsWorld) {
    this.physics = physics
  }

  /**
   * Register wall colliders + door colliders for all houses.
   * Tier-aware: reads house.tier to determine wall dimensions and door position.
   * Door collider ID = memberId (so doorHit.doorId maps directly to enterHouse(memberId)).
   */
  registerHouses(memberHouseMap: Map<string, HouseResult>): void {
    for (const [memberId, house] of memberHouseMap) {
      // Use explicit pivot data (plain numbers, no entity transform dependencies)
      const px = house.pivotX ?? house.entity.getPosition().x
      const pz = house.pivotZ ?? house.entity.getPosition().z
      const yawDeg = house.pivotYaw ?? house.entity.getEulerAngles().y
      const yawRad = yawDeg * Math.PI / 180

      const tierDef = getHouseTier(house.tier ?? 1)

      if (tierDef.exteriorGlb && tierDef.exteriorFootprint) {
        // KayKit house: pivot is at center, collider centered on pivot
        const s = tierDef.exteriorScale ?? 1.0
        const { w, d } = tierDef.exteriorFootprint
        const halfW = (w * s) / 2
        const halfD = (d * s) / 2

        // Wall collider centered on pivot (no local offset needed)
        const boxHalf = rotateHalfSize(halfW, halfD, yawRad)
        this.physics.addStaticBox(
          px, HOUSE_WALL_HEIGHT / 2, pz,
          boxHalf.halfW, HOUSE_WALL_HEIGHT / 2, boxHalf.halfD,
        )

        // Door at front edge: center-local (0, halfD + 0.3)
        const doorLocal = rotatePointYaw(0, halfD + 0.3, yawRad)
        const doorHalf = rotateHalfSize(HOUSE_DOOR_HALF_W, HOUSE_DOOR_HALF_D, yawRad)
        this.physics.addDoor(
          memberId,
          px + doorLocal.x, HOUSE_WALL_HEIGHT / 2, pz + doorLocal.z,
          doorHalf.halfW, HOUSE_WALL_HEIGHT / 2, doorHalf.halfD,
        )
      } else {
        // Kenney house: shift wall boxes from corner-local to center-local
        const ox = -tierDef.width / 2
        const oz = -tierDef.depth / 2
        const doorIdx = TIER_DOOR_INDEX[tierDef.tier] ?? 1
        const walls = computeHutWallBoxes(tierDef.width, tierDef.depth, [doorIdx])

        for (const wall of walls) {
          const shifted: LocalWallBox = {
            minX: wall.minX + ox, maxX: wall.maxX + ox,
            minZ: wall.minZ + oz, maxZ: wall.maxZ + oz,
          }
          this.addRotatedWall(px, pz, yawRad, shifted, HOUSE_WALL_HEIGHT)
        }

        // Door: shift from corner-local to center-local before rotation
        const doorXLocal = ox + doorIdx + 0.5
        const doorZLocal = oz + tierDef.depth
        const doorWorld = rotatePointYaw(doorXLocal, doorZLocal, yawRad)
        const doorHalf = rotateHalfSize(HOUSE_DOOR_HALF_W, HOUSE_DOOR_HALF_D, yawRad)
        this.physics.addDoor(
          memberId,
          px + doorWorld.x, HOUSE_WALL_HEIGHT / 2, pz + doorWorld.z,
          doorHalf.halfW, HOUSE_WALL_HEIGHT / 2, doorHalf.halfD,
        )
      }
    }
  }

  /**
   * Register wall colliders for hut-style buildings (coffee bar, cafeteria, pavilion).
   * These have no door trigger — just blocking walls with open-front gaps.
   */
  registerBuildings(huts: HutInfo[]): void {
    for (const hut of huts) {
      const yawRad = hut.yawDeg * Math.PI / 180
      const walls = computeHutWallBoxes(hut.width, hut.depth, hut.frontDoorIndices)
      for (const wall of walls) {
        this.addRotatedWall(hut.x, hut.z, yawRad, wall, HOUSE_WALL_HEIGHT)
      }
    }
  }

  /**
   * Register a circular pond as a ring of rotated box segments.
   * Player bumps into the ring and can't enter the pond.
   */
  registerPond(pond: PondObstacle, segments = 12): void {
    const segAngle = (2 * Math.PI) / segments
    // Slight overlap (1.15×) ensures no gaps between segments
    const halfW = pond.radius * Math.sin(segAngle / 2) * 1.15
    const halfD = 0.15  // segment thickness
    const halfH = HOUSE_WALL_HEIGHT / 2

    for (let i = 0; i < segments; i++) {
      const angle = i * segAngle
      const cx = pond.x + Math.cos(angle) * pond.radius
      const cz = pond.z + Math.sin(angle) * pond.radius
      // Each segment's local X axis is tangent to the circle
      this.physics.addStaticBoxRotated(
        cx, halfH, cz,
        halfW, halfH, halfD,
        angle + Math.PI / 2,  // tangent direction
      )
    }
  }

  /**
   * Register the world perimeter as a ring of box segments.
   * Prevents the player from walking beyond the world edge.
   */
  registerPerimeter(worldRadius: number, segments = 24): void {
    const segAngle = (2 * Math.PI) / segments
    const halfW = worldRadius * Math.sin(segAngle / 2) * 1.1
    const halfD = 0.5
    const halfH = 2.0

    for (let i = 0; i < segments; i++) {
      const angle = i * segAngle
      const cx = Math.cos(angle) * worldRadius
      const cz = Math.sin(angle) * worldRadius
      this.physics.addStaticBoxRotated(
        cx, halfH, cz,
        halfW, halfH, halfD,
        angle + Math.PI / 2,
      )
    }
  }

  // ─── Private helpers ───────────────────────

  /**
   * Add a wall box at (rootX + rotated local offset, wallCenterY, rootZ + rotated local offset)
   * with half-extents adjusted for the rotation.
   */
  private addRotatedWall(
    rootX: number, rootZ: number, yawRad: number,
    localBox: LocalWallBox, wallHeight: number,
  ): void {
    const centerLocal = {
      x: (localBox.minX + localBox.maxX) / 2,
      z: (localBox.minZ + localBox.maxZ) / 2,
    }
    const centerWorld = rotatePointYaw(centerLocal.x, centerLocal.z, yawRad)
    const half = rotateHalfSize(
      (localBox.maxX - localBox.minX) / 2,
      (localBox.maxZ - localBox.minZ) / 2,
      yawRad,
    )
    this.physics.addStaticBox(
      rootX + centerWorld.x,
      wallHeight / 2,
      rootZ + centerWorld.z,
      half.halfW,
      wallHeight / 2,
      half.halfD,
    )
  }
}

// ─── Pure Helper Functions (exported for testing) ──

/** Local-space wall box, axis-aligned in the hut's local frame. */
export interface LocalWallBox {
  minX: number
  maxX: number
  minZ: number
  maxZ: number
}

/**
 * Compute wall boxes for a hut of size width × depth tiles.
 * Door gaps on the front wall (Z=depth) are skipped.
 *
 * Returns boxes in LOCAL hut coordinates:
 *   back:  Z=0
 *   front: Z=depth
 *   left:  X=0
 *   right: X=width
 *
 * Each tile is 1 unit wide. A door at index i spans X=i to X=i+1.
 */
export function computeHutWallBoxes(
  width: number,
  depth: number,
  frontDoorIndices: number[] = [],
): LocalWallBox[] {
  const boxes: LocalWallBox[] = []
  const t = HOUSE_WALL_THICK

  // Back wall (full span, Z=0)
  boxes.push({ minX: -t, maxX: width + t, minZ: -t, maxZ: t })

  // Left wall (full span, X=0)
  boxes.push({ minX: -t, maxX: t, minZ: -t, maxZ: depth + t })

  // Right wall (full span, X=width)
  boxes.push({ minX: width - t, maxX: width + t, minZ: -t, maxZ: depth + t })

  // Front wall: split into panels around door gaps
  const sortedDoors = [...frontDoorIndices].sort((a, b) => a - b)
  let currentX = 0
  for (const doorIdx of sortedDoors) {
    // Panel before this door (from currentX to doorIdx)
    if (doorIdx > currentX) {
      boxes.push({
        minX: currentX - (currentX === 0 ? t : 0),
        maxX: doorIdx,
        minZ: depth - t,
        maxZ: depth + t,
      })
    }
    currentX = doorIdx + 1  // skip the door tile
  }
  // Final panel after last door (if any tiles remain)
  if (currentX < width) {
    boxes.push({
      minX: currentX,
      maxX: width + t,
      minZ: depth - t,
      maxZ: depth + t,
    })
  }

  return boxes
}

/**
 * Rotate a 2D point (x, z) around origin by yawRad (Y-axis CCW).
 * PlayCanvas uses left-handed Y-up: rotation maps (x, z) → (x·cos + z·sin, -x·sin + z·cos).
 */
export function rotatePointYaw(x: number, z: number, yawRad: number): { x: number; z: number } {
  const c = Math.cos(yawRad)
  const s = Math.sin(yawRad)
  return {
    x: x * c + z * s,
    z: -x * s + z * c,
  }
}

/**
 * Rotate half-extents of an axis-aligned box by yawRad.
 * For axis-aligned rotations (0°, 90°, 180°, 270°), half-extents swap W/D at 90°/270°.
 * For arbitrary angles, returns the AABB containing the rotated box (conservative).
 */
export function rotateHalfSize(
  halfW: number, halfD: number, yawRad: number,
): { halfW: number; halfD: number } {
  const c = Math.abs(Math.cos(yawRad))
  const s = Math.abs(Math.sin(yawRad))
  return {
    halfW: halfW * c + halfD * s,
    halfD: halfW * s + halfD * c,
  }
}
