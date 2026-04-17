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
import type RAPIER_NS from '@dimforge/rapier3d'
import type { PhysicsWorld } from '../physics'
import { WALL_HEIGHT, type HouseResult } from '../buildings/HouseBuilder'
import { getHouseTier } from '../buildings/HouseTierConfig'

// ─── Constants ─────────────────────────────────

/** Single source of truth for wall height — shared with visual HouseBuilder. */
const HOUSE_WALL_HEIGHT = WALL_HEIGHT

const HOUSE_DOOR_HALF_W = 0.45   // slightly narrower than 1-unit door gap
const HOUSE_DOOR_HALF_D = 0.05   // thin trigger
const HOUSE_WALL_THICK = 0.15    // half-thickness of wall boxes

// Door index per tier is read from tierDef.doorIndex — see HouseTierConfig.
// Kept as the single source of truth for wall opening + physics door placement.

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

  /**
   * Rapier bodies registered per house, keyed by memberId. Lets live tier
   * upgrades remove the previous tier's walls/door before registering the new
   * tier's colliders — prevents stale boxes from lingering and trapping the
   * takeover capsule after a rebuild.
   */
  private houseBodies = new Map<string, RAPIER_NS.RigidBody[]>()

  constructor(physics: PhysicsWorld) {
    this.physics = physics
  }

  /**
   * Register wall + door colliders for all houses. Thin loop wrapper —
   * per-house logic lives in `registerHouse` so tier upgrades can re-register
   * a single member without touching the rest.
   */
  registerHouses(memberHouseMap: Map<string, HouseResult>): void {
    for (const [memberId, house] of memberHouseMap) {
      this.registerHouse(memberId, house)
    }
  }

  /**
   * Register wall + door colliders for a single house.
   * Tier-aware: reads house.tier to determine wall dimensions and door position.
   * Door collider ID = memberId (so doorHit.doorId maps directly to enterHouse(memberId)).
   * Pushes every created body into `houseBodies[memberId]` so `removeHouse`
   * can tear them down on tier change.
   */
  registerHouse(memberId: string, house: HouseResult): void {
    // Use explicit pivot data (plain numbers, no entity transform dependencies)
    const px = house.pivotX ?? house.entity.getPosition().x
    const pz = house.pivotZ ?? house.entity.getPosition().z
    const yawDeg = house.pivotYaw ?? house.entity.getEulerAngles().y
    const yawRad = yawDeg * Math.PI / 180

    const tierDef = getHouseTier(house.tier ?? 1)
    const bodies: RAPIER_NS.RigidBody[] = []

    // Diagnostic: surface which tier each house is registered at so we can
    // verify tier-specific collider dimensions in the console.
    console.debug('[TakeoverPhysicsBuilder] registerHouse',
      memberId, 'house.tier=', house.tier, '→ tierDef=', tierDef.name,
      'width=', tierDef.width, 'depth=', tierDef.depth,
      'exteriorFootprint=', tierDef.exteriorFootprint, 'scale=', tierDef.exteriorScale,
      'measuredHalfW=', house.exteriorHalfW, 'measuredHalfD=', house.exteriorHalfD)

    if (tierDef.exteriorGlb && tierDef.exteriorFootprint) {
      // KayKit house: pivot is at center, collider centered on pivot.
      // Prefer the measured GLB footprint (accurate to visual, includes roof
      // overhang) over the static tierDef estimate, which undersizes tier 2/3
      // colliders to roughly the interior floor size.
      const s = tierDef.exteriorScale ?? 1.0
      const halfW = house.exteriorHalfW ?? (tierDef.exteriorFootprint.w * s) / 2
      const halfD = house.exteriorHalfD ?? (tierDef.exteriorFootprint.d * s) / 2

      // Wall collider centered on pivot (no local offset needed)
      const boxHalf = rotateHalfSize(halfW, halfD, yawRad)
      bodies.push(this.physics.addStaticBox(
        px, HOUSE_WALL_HEIGHT / 2, pz,
        boxHalf.halfW, HOUSE_WALL_HEIGHT / 2, boxHalf.halfD,
      ))

      // Door at front edge: center-local (0, halfD + 0.3)
      const doorLocal = rotatePointYaw(0, halfD + 0.3, yawRad)
      const doorHalf = rotateHalfSize(HOUSE_DOOR_HALF_W, HOUSE_DOOR_HALF_D, yawRad)
      bodies.push(this.physics.addDoor(
        memberId,
        px + doorLocal.x, HOUSE_WALL_HEIGHT / 2, pz + doorLocal.z,
        doorHalf.halfW, HOUSE_WALL_HEIGHT / 2, doorHalf.halfD,
      ))
    } else {
      // Kenney house: shift wall boxes from corner-local to center-local
      const ox = -tierDef.width / 2
      const oz = -tierDef.depth / 2
      const doorIdx = tierDef.doorIndex
      const walls = computeHutWallBoxes(tierDef.width, tierDef.depth, [doorIdx])

      for (const wall of walls) {
        const shifted: LocalWallBox = {
          minX: wall.minX + ox, maxX: wall.maxX + ox,
          minZ: wall.minZ + oz, maxZ: wall.maxZ + oz,
        }
        bodies.push(this.addRotatedWall(px, pz, yawRad, shifted, HOUSE_WALL_HEIGHT))
      }

      // Door: shift from corner-local to center-local before rotation
      const doorXLocal = ox + doorIdx + 0.5
      const doorZLocal = oz + tierDef.depth
      const doorWorld = rotatePointYaw(doorXLocal, doorZLocal, yawRad)
      const doorHalf = rotateHalfSize(HOUSE_DOOR_HALF_W, HOUSE_DOOR_HALF_D, yawRad)
      bodies.push(this.physics.addDoor(
        memberId,
        px + doorWorld.x, HOUSE_WALL_HEIGHT / 2, pz + doorWorld.z,
        doorHalf.halfW, HOUSE_WALL_HEIGHT / 2, doorHalf.halfD,
      ))
    }

    this.houseBodies.set(memberId, bodies)
  }

  /**
   * Remove all colliders previously registered for `memberId`. Safe to call
   * for an unknown id (no-op). Pair with `registerHouse` to rebuild physics
   * after a visual tier change so the collider matches the new footprint.
   */
  removeHouse(memberId: string): void {
    const bodies = this.houseBodies.get(memberId)
    if (!bodies) return
    for (const body of bodies) {
      this.physics.removeBody(body)
    }
    this.houseBodies.delete(memberId)
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
    this.addPhysicsRing(pond.x, pond.z, pond.radius, {
      halfH: HOUSE_WALL_HEIGHT / 2,
      thickness: 0.15,
      segments,
      overlap: 1.15,
    })
  }

  /**
   * Register the world perimeter as a ring of box segments.
   * Prevents the player from walking beyond the world edge.
   */
  registerPerimeter(worldRadius: number, segments = 24): void {
    this.addPhysicsRing(0, 0, worldRadius, {
      halfH: 2.0,
      thickness: 0.5,
      segments,
      overlap: 1.1,
    })
  }

  // ─── Private helpers ───────────────────────

  /**
   * Build a ring of rotated box segments at (cx, cz) with the given radius.
   *
   * Convention matches CircularFence (visual): x = sin(angle) * r,
   * z = cos(angle) * r, yaw = angle. angle=0 starts at +Z and sweeps
   * clockwise — so physics rings overlap visual fence posts exactly.
   *
   * Each segment's tangent half-width is computed from the arc length so
   * adjacent segments overlap by `overlap` (default 1.1×) to prevent gaps.
   * The box bottom sits at y=0 and top at y=2×halfH.
   */
  private addPhysicsRing(
    cx: number, cz: number, radius: number,
    opts: { halfH: number; thickness: number; segments: number; overlap?: number },
  ): void {
    const { halfH, thickness, segments, overlap = 1.1 } = opts
    const segAngle = (2 * Math.PI) / segments
    const halfW = radius * Math.sin(segAngle / 2) * overlap

    for (let i = 0; i < segments; i++) {
      const angle = i * segAngle
      this.physics.addStaticBoxRotated(
        cx + Math.sin(angle) * radius,
        halfH,
        cz + Math.cos(angle) * radius,
        halfW, halfH, thickness,
        angle,
      )
    }
  }

  /**
   * Add a wall box at (rootX + rotated local offset, wallCenterY, rootZ + rotated local offset)
   * with half-extents adjusted for the rotation.
   */
  private addRotatedWall(
    rootX: number, rootZ: number, yawRad: number,
    localBox: LocalWallBox, wallHeight: number,
  ): RAPIER_NS.RigidBody {
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
    return this.physics.addStaticBox(
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
