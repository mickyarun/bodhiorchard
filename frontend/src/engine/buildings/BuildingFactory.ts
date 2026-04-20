// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * BuildingFactory — Shared building construction helpers.
 *
 * Provides reusable functions for creating floors, walls, placing furniture,
 * and constructing roofs from Kenney Furniture Kit GLBs.
 */
import * as pc from 'playcanvas'
import { AssetLoader } from '../assets/AssetLoader'
import { BUILDING } from '../assets/AssetManifest'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { InteractionPoint, InteractionAnim } from '../characters/InteractionPoint'
import { SEAT_OFFSETS } from '../characters/InteractionPoint'
import { SeatProber } from '../characters/SeatProber'

/** Kenney tile size — 1×1 units confirmed by GLB measurements + starter kit. */
const TILE_SIZE = 1

/** String light definition in LOCAL coordinates relative to the building root. */
export interface LightString {
  start: { x: number; y: number; z: number }
  end: { x: number; y: number; z: number }
  bulbCount: number
}

const BULB_RADIUS = 0.12
const WIRE_BEAD_SIZE = 0.04
const WIRE_SPACING = 0.15
const POLE_WIDTH = 0.08
const SAG_RATIO = 0.1

export class BuildingFactory {
  private loader: AssetLoader
  private materials: MaterialFactory | null

  constructor(loader: AssetLoader, materials?: MaterialFactory) {
    this.loader = loader
    this.materials = materials ?? null
  }

  /** Exposes the shared material cache so subsystems (e.g. ExteriorScene) can create
   *  properly-lit cached materials without creating a separate MaterialFactory instance. */
  get materialFactory(): MaterialFactory | null { return this.materials }

  /** Shared GLB loader — exposed so subsystems can implement alternative
   *  placement strategies (e.g. world-AABB auto-fit for packs whose GLBs bake
   *  node-level scale transforms). */
  get assetLoader(): AssetLoader { return this.loader }

  /**
   * Create a tiled floor from floorFull GLBs.
   * @param parent Parent entity to add floor tiles to
   * @param width Number of tiles wide
   * @param depth Number of tiles deep
   * @param offsetX X offset for floor origin
   * @param offsetZ Z offset for floor origin
   */
  async createFloor(
    parent: pc.Entity,
    width: number,
    depth: number,
    offsetX = 0,
    offsetZ = 0,
  ): Promise<void> {
    const asset = await this.loader.load(BUILDING.floorFull)
    for (let x = 0; x < width; x++) {
      for (let z = 0; z < depth; z++) {
        const tile = this.loader.instance(asset)
        // Floor tiles extend -Z from origin (bbox z=[-1,0]).
        // Shift Z by +1 so tile at z=0 covers [0,1] instead of [-1,0],
        // aligning floor with walls which bound [0, depth].
        tile.setLocalPosition(
          offsetX + x * TILE_SIZE,
          0,
          offsetZ + (z + 1) * TILE_SIZE,
        )
        parent.addChild(tile)
      }
    }
  }

  /**
   * Create walls around a rectangular area.
   * @param parent Parent entity
   * @param width Tiles wide (X axis)
   * @param depth Tiles deep (Z axis)
   * @param openings Array of {side, index} where doors/windows go
   */
  async createWalls(
    parent: pc.Entity,
    width: number,
    depth: number,
    openings: Array<{ side: 'front' | 'back' | 'left' | 'right'; index: number; type: 'door' | 'window' }> = [],
  ): Promise<void> {
    const wallAsset = await this.loader.load(BUILDING.wall)
    const windowAsset = await this.loader.load(BUILDING.wallWindow)
    const doorAsset = await this.loader.load(BUILDING.wallDoorway)

    const getAsset = (side: string, idx: number) => {
      const opening = openings.find(o => o.side === side && o.index === idx)
      if (!opening) return wallAsset
      return opening.type === 'door' ? doorAsset : windowAsset
    }

    // Back wall (z = 0, no rotation — wall extends in +X from pivot)
    for (let x = 0; x < width; x++) {
      const asset = getAsset('back', x)
      const wall = this.loader.instance(asset)
      wall.setLocalPosition(x * TILE_SIZE, 0, 0)
      parent.addChild(wall)
    }

    // Front wall (z = depth, rotated 180° — pivot offset +1 to compensate rotation)
    for (let x = 0; x < width; x++) {
      const asset = getAsset('front', x)
      const wall = this.loader.instance(asset)
      wall.setLocalPosition((x + 1) * TILE_SIZE, 0, depth * TILE_SIZE)
      wall.setLocalEulerAngles(0, 180, 0)
      parent.addChild(wall)
    }

    // Left wall (x = 0, rotated 90° — pivot offset +1 in Z to compensate rotation)
    for (let z = 0; z < depth; z++) {
      const asset = getAsset('left', z)
      const wall = this.loader.instance(asset)
      wall.setLocalPosition(0, 0, (z + 1) * TILE_SIZE)
      wall.setLocalEulerAngles(0, 90, 0)
      parent.addChild(wall)
    }

    // Right wall (x = width, rotated -90° — extends correctly in +Z from pivot)
    for (let z = 0; z < depth; z++) {
      const asset = getAsset('right', z)
      const wall = this.loader.instance(asset)
      wall.setLocalPosition(width * TILE_SIZE, 0, z * TILE_SIZE)
      wall.setLocalEulerAngles(0, -90, 0)
      parent.addChild(wall)
    }
  }

  /**
   * Place a furniture GLB at a raw position (no AABB correction).
   * Use placeFurnitureCentered() for automatic center-alignment.
   */
  async placeFurniture(
    parent: pc.Entity,
    assetPath: string,
    x: number,
    y: number,
    z: number,
    yaw = 0,
  ): Promise<pc.Entity> {
    const asset = await this.loader.load(assetPath)
    const instance = this.loader.instance(asset)
    instance.setLocalPosition(x, y, z)
    if (yaw !== 0) instance.setLocalEulerAngles(0, yaw, 0)
    parent.addChild(instance)
    return instance
  }

  /**
   * Place furniture with automatic AABB center-alignment.
   *
   * Uses Mesh.aabb (local/model-space) for centering — computed from vertex
   * data at load time, so it's always valid regardless of scene graph state.
   * Same approach as getEntityHeight().
   *
   * 1. Compute local-space AABB from Mesh.aabb
   * 2. Offset model so center-bottom aligns with wrapper origin
   * 3. Position wrapper, apply rotation, attach to parent
   *
   * Usage: placeFurnitureCentered(root, BUILDING.bedSingle, 2, 0, 1)
   * → bed's visual center is at (2, 0, 1), bottom on floor.
   */
  async placeFurnitureCentered(
    parent: pc.Entity,
    assetPath: string,
    centerX: number,
    y: number,
    centerZ: number,
    yaw = 0,
  ): Promise<pc.Entity> {
    const asset = await this.loader.load(assetPath)
    const model = this.loader.instance(asset)

    // Compute AABB from Mesh.aabb (local/model-space, always valid).
    // Unlike MeshInstance.aabb (world-space), this doesn't need the entity
    // to be in the scene graph — same approach as getEntityHeight().
    const renders = model.findComponents('render') as pc.RenderComponent[]
    const meshInstances = renders.flatMap(
      (rc: pc.RenderComponent) => rc.meshInstances,
    )

    const wrapper = new pc.Entity('Furniture')
    wrapper.addChild(model)

    if (meshInstances.length > 0) {
      const aabb = new pc.BoundingBox()
      aabb.copy(meshInstances[0].mesh.aabb)
      for (let i = 1; i < meshInstances.length; i++) {
        aabb.add(meshInstances[i].mesh.aabb)
      }

      // Offset model so center-bottom sits at wrapper origin.
      // All coordinates are in model-local space — no world transform needed.
      model.setLocalPosition(
        -aabb.center.x,
        -aabb.getMin().y,
        -aabb.center.z,
      )
    }

    // Position wrapper, apply rotation, attach to parent
    wrapper.setLocalPosition(centerX, y, centerZ)
    if (yaw !== 0) wrapper.setLocalEulerAngles(0, yaw, 0)
    parent.addChild(wrapper)

    return wrapper
  }

  /** Create a simple flat roof using a box primitive. */
  createRoof(
    parent: pc.Entity,
    width: number,
    depth: number,
    height: number,
  ): pc.Entity {
    const roof = new pc.Entity('Roof')
    roof.addComponent('render', { type: 'box' })
    roof.setLocalScale(width * TILE_SIZE, 0.08, depth * TILE_SIZE)
    roof.setLocalPosition(
      (width * TILE_SIZE) / 2,
      height,
      (depth * TILE_SIZE) / 2,
    )
    parent.addChild(roof)
    return roof
  }

  /**
   * Get the model-space height of a placed entity.
   *
   * Uses Mesh.aabb (local/model space) NOT MeshInstance.aabb (world space).
   * Model-space AABB is computed from vertex data at load time and is always
   * valid — no scene graph or render pass required.
   *
   * Kenney models start at y=0, so mesh.aabb.getMax().y = model height.
   */
  static getEntityHeight(entity: pc.Entity): number {
    const renders = entity.findComponents('render') as pc.RenderComponent[]
    const meshInstances = renders.flatMap(
      (rc: pc.RenderComponent) => rc.meshInstances,
    )
    if (meshInstances.length === 0) return 0

    let maxY = 0
    for (const mi of meshInstances) {
      const meshTop = mi.mesh.aabb.getMax().y
      if (meshTop > maxY) maxY = meshTop
    }
    return maxY
  }

  /**
   * Get the model-space XZ footprint of a placed entity as half-extents.
   *
   * Unions every Mesh.aabb on the entity (local/model space — always valid
   * without a render pass) so the returned half-extents cover the full visual
   * exterior, including roof overhangs and porches. Callers scale the result
   * by the entity's local scale to obtain the world-space footprint.
   *
   * Returns { halfW: 0, halfD: 0 } for entities with no render meshes.
   */
  static getEntityFootprint(entity: pc.Entity): { halfW: number; halfD: number } {
    const renders = entity.findComponents('render') as pc.RenderComponent[]
    const meshInstances = renders.flatMap(
      (rc: pc.RenderComponent) => rc.meshInstances,
    )
    if (meshInstances.length === 0) return { halfW: 0, halfD: 0 }

    const aabb = new pc.BoundingBox()
    aabb.copy(meshInstances[0].mesh.aabb)
    for (let i = 1; i < meshInstances.length; i++) {
      aabb.add(meshInstances[i].mesh.aabb)
    }
    const he = aabb.halfExtents
    return { halfW: he.x, halfD: he.z }
  }

  /**
   * Create string lights as children of a building entity.
   * All coordinates are LOCAL to the parent.
   *
   * Uses only boxes (poles) and spheres (wire beads + bulbs) — no rotation
   * math, no cylinders, no quaternion complexity. Dead-simple geometry.
   */
  createStringLights(parent: pc.Entity, strings: LightString[]): void {
    if (!this.materials) return

    const bulbMat = this.materials.getColor('sl_bulb', 1, 0.9, 0.5, {
      emissive: [1, 0.85, 0.4],
    })
    const wireMat = this.materials.getColor('sl_wire', 0.18, 0.12, 0.08)
    const poleMat = this.materials.getColor('sl_pole', 0.35, 0.22, 0.12)

    const lightsRoot = new pc.Entity('StringLights')
    parent.addChild(lightsRoot)

    for (const str of strings) {
      const dx = str.end.x - str.start.x
      const dz = str.end.z - str.start.z
      const span = Math.sqrt(dx * dx + dz * dz)
      const sag = span * SAG_RATIO

      // ─── Poles: box from y=0 to y=poleTop ───
      // Default box is 1×1×1 centered at origin.
      // Scale(w, h, w) + position(x, h/2, z) → bottom at y=0, top at y=h.
      for (const p of [str.start, str.end]) {
        const pole = new pc.Entity('Pole')
        pole.addComponent('render', { type: 'box' })
        pole.setLocalScale(POLE_WIDTH, p.y, POLE_WIDTH)
        pole.setLocalPosition(p.x, p.y / 2, p.z)
        pole.render!.meshInstances[0].material = poleMat
        lightsRoot.addChild(pole)
      }

      // ─── Catenary helper: point at parameter t ∈ [0, 1] ───
      const catenary = (t: number) => ({
        x: str.start.x + dx * t,
        y: str.start.y + (str.end.y - str.start.y) * t
          - Math.sin(t * Math.PI) * sag,
        z: str.start.z + dz * t,
      })

      // ─── Wire: small dark spheres along catenary ───
      const beadCount = Math.max(3, Math.floor(span / WIRE_SPACING))
      for (let i = 0; i <= beadCount; i++) {
        const pt = catenary(i / beadCount)
        const bead = new pc.Entity('WireBead')
        bead.addComponent('render', { type: 'sphere' })
        bead.setLocalScale(WIRE_BEAD_SIZE, WIRE_BEAD_SIZE, WIRE_BEAD_SIZE)
        bead.setLocalPosition(pt.x, pt.y, pt.z)
        bead.render!.meshInstances[0].material = wireMat
        lightsRoot.addChild(bead)
      }

      // ─── Bulbs: larger emissive spheres at even intervals ───
      for (let i = 0; i < str.bulbCount; i++) {
        const t = (i + 0.5) / str.bulbCount
        const pt = catenary(t)
        const bulb = new pc.Entity('Bulb')
        bulb.addComponent('render', { type: 'sphere' })
        bulb.setLocalScale(BULB_RADIUS * 2, BULB_RADIUS * 2, BULB_RADIUS * 2)
        bulb.setLocalPosition(pt.x, pt.y, pt.z)
        bulb.render!.meshInstances[0].material = bulbMat
        lightsRoot.addChild(bulb)
      }
    }
  }

  /**
   * Create a procedural beach parasol (pole + dome-shaped cone canopy + finial).
   * All coords are LOCAL to parent.
   *
   * Proportions tuned for poolside use:
   * - Pole: thin wooden stick, ground to canopy base
   * - Canopy: inverted cone with enough height to look dome-like (~2:1 diameter:height)
   * - Finial: small sphere on top for classic parasol silhouette
   *
   * `canopyColor` + `cacheKey` let callers create multi-colored umbrella
   * sets (e.g. poolside) without colliding on the shared 'umbrella_canopy'
   * material cache entry. Omit both for the default red cafeteria parasol.
   */
  createUmbrella(
    parent: pc.Entity,
    x: number,
    z: number,
    baseY = 0,
    poleHeight = 1.8,
    canopyRadius = 0.65,
    canopyColor: [number, number, number] = [0.82, 0.18, 0.12],
    cacheKey = 'umbrella_canopy',
  ): void {
    if (!this.materials) return

    const poleMat = this.materials.getColor('umbrella_pole', 0.45, 0.3, 0.18)
    const canopyMat = this.materials.getColor(cacheKey, ...canopyColor)

    const umbrella = new pc.Entity('Umbrella')
    umbrella.setLocalPosition(x, baseY, z)

    // Pole: thin box from ground to canopy base
    const pole = new pc.Entity('Pole')
    pole.addComponent('render', { type: 'box' })
    pole.setLocalScale(0.05, poleHeight, 0.05)
    pole.setLocalPosition(0, poleHeight / 2, 0)
    pole.render!.meshInstances[0].material = poleMat
    umbrella.addChild(pole)

    // Canopy: upright cone — apex at top (umbrella finial), base at bottom
    // (where the ribs splay out). PlayCanvas cones have apex at +Y by
    // default; with scale(h) the cone extends ±h/2 about its center, so
    // placing the entity at poleHeight + canopyH/2 seats the base on the
    // pole-top and leaves the finial at poleHeight + canopyH.
    const canopyH = 0.45
    const canopy = new pc.Entity('Canopy')
    canopy.addComponent('render', { type: 'cone' })
    canopy.setLocalScale(canopyRadius * 2, canopyH, canopyRadius * 2)
    canopy.setLocalPosition(0, poleHeight + canopyH / 2, 0)
    canopy.render!.meshInstances[0].material = canopyMat
    umbrella.addChild(canopy)

    // Finial: small sphere atop the cone's apex for classic parasol look
    const finial = new pc.Entity('Finial')
    finial.addComponent('render', { type: 'sphere' })
    finial.setLocalScale(0.08, 0.08, 0.08)
    finial.setLocalPosition(0, poleHeight + canopyH + 0.04, 0)
    finial.render!.meshInstances[0].material = poleMat
    umbrella.addChild(finial)

    parent.addChild(umbrella)
  }

  /** Generate a unique seat ID. */
  static seatId(zone: string, index: number): string {
    return `${zone}_seat_${index}`
  }

  /**
   * Place furniture and create an interaction seat in one call.
   *
   * Combines placeFurnitureCentered + SeatProber + createInteractionSeat:
   *   1. Places the furniture GLB at (localX, baseY, localZ) inside parent
   *   2. Probes actual seat surface Y from mesh vertex geometry
   *   3. Creates an InteractionPoint at the correct world position + height
   *
   * Use this for any chair/bench that characters will sit on. For furniture
   * with custom placement (e.g. PoolResortBuilder's umbrellaSet), call
   * createInteractionSeat directly with an explicit probedSeatY.
   */
  async placeSeat(
    parent: pc.Entity,
    assetPath: string,
    localX: number,
    localZ: number,
    yaw: number,
    zone: string,
    seatIndex: number,
    worldOriginX: number,
    worldOriginZ: number,
    furnitureType: string,
    anim: InteractionAnim = 'sit',
    baseY = 0,
  ): Promise<{ entity: pc.Entity; seat: InteractionPoint }> {
    const entity = await this.placeFurnitureCentered(
      parent, assetPath, localX, baseY, localZ, yaw,
    )
    const probedY = SeatProber.probeSeatY(entity)
    const seat = BuildingFactory.createInteractionSeat(
      zone, seatIndex,
      worldOriginX + localX, worldOriginZ + localZ,
      yaw, furnitureType, anim, baseY, probedY ?? undefined,
    )
    return { entity, seat }
  }

  /**
   * Create an InteractionPoint at the correct seat surface position.
   *
   * Uses forwardOffset from SEAT_OFFSETS to correct for the backrest
   * shifting the AABB center backward. Seat height is taken from
   * probedSeatY (geometry-detected) or SEAT_OFFSETS.seatY (fallback).
   *
   * @param probedSeatY - Geometry-detected seat height from SeatProber.
   *   If undefined, falls back to SEAT_OFFSETS[furnitureType].seatY.
   */
  static createInteractionSeat(
    zone: string,
    index: number,
    furnitureCenterX: number,
    furnitureCenterZ: number,
    yaw: number,
    furnitureType: string,
    anim: InteractionAnim = 'sit',
    baseY = 0,
    probedSeatY?: number,
  ): InteractionPoint {
    const offsets = SEAT_OFFSETS[furnitureType] ?? { forwardOffset: 0, seatY: 0.4 }
    const seatY = probedSeatY ?? offsets.seatY
    const yawRad = (yaw * Math.PI) / 180
    const fwdX = Math.sin(yawRad)
    const fwdZ = Math.cos(yawRad)

    const seatX = furnitureCenterX + fwdX * offsets.forwardOffset
    const seatZ = furnitureCenterZ + fwdZ * offsets.forwardOffset

    const approachDist = offsets.forwardOffset + 0.5
    return {
      id: BuildingFactory.seatId(zone, index),
      zone,
      x: seatX,
      y: baseY + seatY,
      z: seatZ,
      yaw,
      anim,
      approachX: furnitureCenterX + fwdX * approachDist,
      approachZ: furnitureCenterZ + fwdZ * approachDist,
      occupied: false,
    }
  }
}
