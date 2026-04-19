// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * StandupPavilion — Open-air campfire standup area.
 *
 * Layout (top-down, concentric rings around the campfire):
 *
 *                   post               post
 *                    ·     ┌────┐       ·
 *                          │ T4 │
 *                          └────┘
 *            ┌────┐  [stand]    [stand]  ┌────┐
 *            │ T1 │              ·       │ T3 │
 *            └────┘   🔥 campfire         └────┘
 *                     stones + logs
 *            ┌────┐  [stand]    [stand]  ┌────┐
 *            │    │                      │    │
 *                          ┌────┐
 *                          │ T2 │
 *                    ·     └────┘       ·
 *                   post               post
 *
 * The pavilion is a casual gathering spot: a ring of small round tables
 * around a central campfire, standing spots for team members, and four
 * decorative corner posts linked by warm string lights. No walls, no roof —
 * deliberately open-air so players can walk freely around the fire.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from './BuildingFactory'
import { BUILDING, CAMPFIRE } from '../assets/AssetManifest'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { ExclusionZone } from '../utils/MathUtils'

/** One animated "flame tongue" — tracked for per-frame updates. */
interface FlameTongue {
  entity: pc.Entity
  baseX: number
  baseY: number
  baseZ: number
  baseScale: number
  phase: number
  rate: number
}

export interface PavilionResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
  /**
   * Hut dimensions for takeover physics wall generation.
   * `undefined` for the open-air standup area — there are no walls to collide with.
   */
  hutDims?: { width: number; depth: number; frontDoorIndices: number[] }
}

// ─── Layout tuning (all in local pavilion units) ──────────────────────────
const AREA_RADIUS = 4.5           // visual stone patch radius
const TABLE_RING_RADIUS = 1.8     // distance from campfire to each table
const STAND_RING_RADIUS = 2.55    // distance from campfire to each standing spot
const POST_RING_RADIUS = 3.6      // distance from campfire to each decorative post
const TABLE_COUNT = 4
const STAND_COUNT = 4
const POST_COUNT = 4
const POST_HEIGHT = 2.5
const POST_THICKNESS = 0.12

// ─── Fireplace tuning ─────────────────────────────────────────────────────
const FIREPLACE_TARGET_WIDTH = 1.6   // target world-space footprint diameter
const FLAME_COUNT = 5                // number of animated flame tongues

export class StandupPavilion {
  private factory: BuildingFactory
  private materials: pc.StandardMaterial[] = []
  private flames: FlameTongue[] = []
  private fireLight: pc.LightComponent | null = null
  private updateHandler: ((dt: number) => void) | null = null
  private pcApp: pc.AppBase | null = null
  private fireT = 0   // elapsed time for flame animation

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  /** Destroy all GPU materials + unregister per-frame update handler. */
  destroy(): void {
    if (this.updateHandler && this.pcApp) {
      this.pcApp.off('update', this.updateHandler)
    }
    this.updateHandler = null
    this.pcApp = null
    this.flames = []
    this.fireLight = null
    for (const mat of this.materials) mat.destroy()
    this.materials = []
  }

  async build(app: Application, x: number, z: number): Promise<PavilionResult> {
    const root = new pc.Entity('StandupPavilion')
    root.setPosition(x, 0, z)

    const seats: InteractionPoint[] = []

    // ─── Stone floor patch (decorative disc) ───
    this.createStonePatch(root, AREA_RADIUS)

    // ─── Fireplace at center (external Sketchfab GLB, needs rescale) ───
    const fireplaceHeight = await this.loadFireplace(root)

    // ─── Animated procedural flames above the log bowl ───
    // Log bowl sits at roughly 25% of the fireplace height — this is where
    // the flames should appear to emerge from.
    const flameBaseY = fireplaceHeight * 0.25
    this.createFlames(root, flameBaseY)

    // ─── Warm omni glow (flickers in sync with the flames) ───
    this.createFireGlow(root, flameBaseY + 0.3)

    // ─── Ring of 4 small round tables around the campfire ───
    // Tables sit at cardinal compass points (N, E, S, W) so standing spots
    // can slot in on the diagonals.
    for (let i = 0; i < TABLE_COUNT; i++) {
      const theta = (i / TABLE_COUNT) * Math.PI * 2
      const tx = Math.cos(theta) * TABLE_RING_RADIUS
      const tz = Math.sin(theta) * TABLE_RING_RADIUS
      // Yaw so the table's local +Z axis points at the campfire.
      // (+Z is the "face" direction after placeFurnitureCentered.)
      const yaw = this.yawFacingCenter(tx, tz)
      await this.factory.placeFurnitureCentered(
        root, BUILDING.tableCoffee, tx, 0, tz, yaw,
      )
    }

    // ─── Standing spots between the tables (diagonals) ───
    // Offset by half a table-step so standers don't overlap tables.
    const standAngleOffset = (Math.PI * 2) / (TABLE_COUNT * 2)  // 45°
    let seatIndex = 0
    for (let i = 0; i < STAND_COUNT; i++) {
      const theta = (i / STAND_COUNT) * Math.PI * 2 + standAngleOffset
      const sx = Math.cos(theta) * STAND_RING_RADIUS
      const sz = Math.sin(theta) * STAND_RING_RADIUS
      const yaw = this.yawFacingCenter(sx, sz)
      seats.push(BuildingFactory.createInteractionSeat(
        'pavilion', seatIndex++,
        x + sx, z + sz,
        yaw, 'standingSpot', 'idle',
      ))
    }

    // ─── Decorative corner posts (open-air frame) ───
    const postPositions: Array<{ lx: number; lz: number }> = []
    for (let i = 0; i < POST_COUNT; i++) {
      const theta = (i / POST_COUNT) * Math.PI * 2 + Math.PI / 4  // diagonals
      const px = Math.cos(theta) * POST_RING_RADIUS
      const pz = Math.sin(theta) * POST_RING_RADIUS
      this.createPost(root, px, pz)
      postPositions.push({ lx: px, lz: pz })
    }

    // ─── String lights strung post → post around the ring ───
    const stringY = POST_HEIGHT - 0.1
    const stringSegments = postPositions.map((start, i) => {
      const end = postPositions[(i + 1) % postPositions.length]
      return {
        start: { x: start.lx, y: stringY, z: start.lz },
        end: { x: end.lx, y: stringY, z: end.lz },
        bulbCount: 4,
      }
    })
    this.factory.createStringLights(root, stringSegments)

    app.root.addChild(root)

    // ─── Per-frame flame animation ───
    // Store the pc.AppBase reference + bound handler so destroy() can unregister.
    this.pcApp = app.app
    this.updateHandler = (dt: number) => this.tickFlames(dt)
    app.app.on('update', this.updateHandler)

    return {
      entity: root,
      exclusionZone: { x, z, radius: AREA_RADIUS + 0.5 },
      seats,
      // No hutDims → SceneManager skips physics wall registration.
    }
  }

  // ─── Helpers ──────────────────────────────────────────────────────────────

  /**
   * Yaw (in degrees) for an entity placed at local (lx, lz) that should
   * face the center (0, 0). placeFurnitureCentered leaves the model's face
   * pointing at +Z, so we need the angle whose +Z points toward origin.
   */
  private yawFacingCenter(lx: number, lz: number): number {
    // atan2(dx, dz) gives the yaw whose +Z direction matches (dx, dz).
    // We want +Z to point from (lx, lz) → (0, 0), i.e. direction (-lx, -lz).
    return Math.atan2(-lx, -lz) * (180 / Math.PI)
  }

  /**
   * Create an 8-sided stone-colored disc as the pavilion floor patch.
   * Pure procedural geometry — no GLB load — to keep the visual consistent
   * with the existing `pavilion` ground paint in GroundSystem.
   */
  private createStonePatch(parent: pc.Entity, radius: number): void {
    const patch = new pc.Entity('StonePatch')
    patch.addComponent('render', { type: 'cylinder' })
    // PlayCanvas cylinder primitive is unit height centered at origin;
    // scale Y down so it's a thin pad sitting just above ground.
    patch.setLocalScale(radius * 2, 0.02, radius * 2)
    patch.setLocalPosition(0, 0.01, 0)

    const mat = new pc.StandardMaterial()
    this.materials.push(mat)
    mat.diffuse = new pc.Color(0.62, 0.60, 0.56)   // warm grey stone
    mat.metalness = 0
    mat.gloss = 0.15
    mat.update()
    patch.render!.meshInstances[0].material = mat
    patch.render!.castShadows = false
    parent.addChild(patch)
  }

  /**
   * Warm omni light at the campfire center to simulate fire glow.
   * The intensity is modulated per-frame by tickFlames() for a flicker effect.
   */
  private createFireGlow(parent: pc.Entity, y: number): void {
    const fire = new pc.Entity('FireGlow')
    fire.addComponent('light', {
      type: 'omni',
      color: new pc.Color(1.0, 0.65, 0.3),   // orange-amber
      intensity: 2.2,
      range: 5.5,
      castShadows: false,
    })
    fire.setLocalPosition(0, y, 0)
    parent.addChild(fire)
    this.fireLight = fire.light ?? null
    // When the fire entity is destroyed (e.g., parent scene teardown without
    // StandupPavilion.destroy() being called), null out the ref so tickFlames
    // doesn't poke at a detached LightComponent whose internal _light is null.
    fire.once('destroy', () => { this.fireLight = null })
  }

  // ─── Fireplace GLB loader ────────────────────────────────────────────────

  /**
   * Load the external Sketchfab fireplace GLB, fix its axis + scale, and
   * return the resulting world-space height so callers know where to place
   * flames on top of it.
   *
   * Sketchfab exports come with two quirks we handle here:
   *   1. A 100× scale matrix on the root node (FBX cm → m baked in)
   *   2. Z-up orientation inherited from FBX (glTF spec is Y-up)
   *
   * Strategy:
   *   1. placeFurniture() at (0,0,0) — this loads + instances + attaches to parent
   *   2. Rotate the returned entity −90° around X (Z-up → Y-up)
   *   3. Measure the world-space AABB from every MeshInstance
   *   4. Uniform-scale so max(width, depth) = FIREPLACE_TARGET_WIDTH
   *   5. Remeasure after scale, then offset so the base sits on the ground
   *      and the footprint centers on the parent origin
   */
  private async loadFireplace(parent: pc.Entity): Promise<number> {
    const model = await this.factory.placeFurniture(
      parent, CAMPFIRE.fireplace, 0, 0, 0,
    )
    // Source model is Z-up (FBX legacy). Rotate so its up axis becomes +Y.
    model.setLocalEulerAngles(-90, 0, 0)

    // MeshInstance.aabb is only valid once the entity is in the scene graph
    // AND its world transform has been resolved — which we force below.
    model.getWorldTransform()
    const meshInstances = this.collectMeshInstances(model)
    if (meshInstances.length === 0) return 1.0

    // 1st measurement: raw footprint after axis rotation, before scaling.
    const rawAabb = this.worldAabb(meshInstances)
    const rawMax = Math.max(rawAabb.halfExtents.x, rawAabb.halfExtents.z) * 2
    const scale = rawMax > 0 ? FIREPLACE_TARGET_WIDTH / rawMax : 1
    model.setLocalScale(scale, scale, scale)
    model.getWorldTransform()

    // 2nd measurement: now we know where the scaled footprint actually sits
    // so we can offset to center + drop the base onto the ground.
    const scaledAabb = this.worldAabb(meshInstances)
    const parentPos = parent.getPosition()
    const dx = scaledAabb.center.x - parentPos.x
    const dz = scaledAabb.center.z - parentPos.z
    const dy = (scaledAabb.center.y - scaledAabb.halfExtents.y) - parentPos.y
    const prev = model.getLocalPosition()
    model.setLocalPosition(prev.x - dx, prev.y - dy, prev.z - dz)
    model.getWorldTransform()

    // Final AABB gives us the finished world-space height (for flame placement).
    const finalAabb = this.worldAabb(meshInstances)
    return finalAabb.halfExtents.y * 2
  }

  /** Recursively collect every MeshInstance under `entity`. */
  private collectMeshInstances(entity: pc.Entity): pc.MeshInstance[] {
    const out: pc.MeshInstance[] = []
    const renders = entity.findComponents('render') as pc.RenderComponent[]
    for (const rc of renders) out.push(...rc.meshInstances)
    return out
  }

  /** Compute the world-space AABB enclosing every MeshInstance. */
  private worldAabb(instances: pc.MeshInstance[]): pc.BoundingBox {
    const aabb = new pc.BoundingBox()
    aabb.copy(instances[0].aabb)
    for (let i = 1; i < instances.length; i++) {
      aabb.add(instances[i].aabb)
    }
    return aabb
  }

  // ─── Procedural flame animation ──────────────────────────────────────────

  /**
   * Create a cluster of emissive "flame tongue" spheres above the log bowl.
   * Each flame gets its own phase + rate so they flicker independently, and
   * we track them in `this.flames` so the update loop can animate them.
   */
  private createFlames(parent: pc.Entity, y: number): void {
    // One shared emissive material for all flame tongues — cheap, and the
    // per-frame scaling + position changes give the illusion of individual
    // flames. Uses emissive (not diffuse) so the color stays bright even in
    // the shadow cast by the stands.
    const flameMat = new pc.StandardMaterial()
    this.materials.push(flameMat)
    flameMat.diffuse = new pc.Color(1.0, 0.35, 0.05)
    flameMat.emissive = new pc.Color(1.0, 0.55, 0.1)
    flameMat.emissiveIntensity = 2.0
    flameMat.metalness = 0
    flameMat.gloss = 0.1
    flameMat.opacity = 0.88
    flameMat.blendType = pc.BLEND_NORMAL
    flameMat.update()

    for (let i = 0; i < FLAME_COUNT; i++) {
      // Tight cluster inside the log bowl — slight x/z jitter and one
      // taller flame at the center for the "main tongue" look.
      const isCenter = i === 0
      const angle = (i / FLAME_COUNT) * Math.PI * 2
      const radius = isCenter ? 0 : 0.12
      const lx = Math.cos(angle) * radius
      const lz = Math.sin(angle) * radius
      const baseScale = isCenter ? 0.45 : 0.3

      const flame = new pc.Entity(`Flame${i}`)
      flame.addComponent('render', { type: 'sphere' })
      flame.render!.meshInstances[0].material = flameMat
      flame.render!.castShadows = false
      flame.setLocalPosition(lx, y + baseScale * 0.6, lz)
      flame.setLocalScale(baseScale * 0.7, baseScale * 1.6, baseScale * 0.7)
      parent.addChild(flame)

      this.flames.push({
        entity: flame,
        baseX: lx,
        baseY: y,
        baseZ: lz,
        baseScale,
        phase: Math.random() * Math.PI * 2,
        rate: 6 + Math.random() * 4,  // cycles/sec — slightly different per flame
      })
    }
  }

  /**
   * Per-frame flame + glow animation. Called from the pc.Application update
   * event. Uses simple sin-based oscillation with per-flame phase for a
   * convincing flicker without a particle system.
   */
  private tickFlames(dt: number): void {
    if (!this.pcApp) return  // destroyed — stale handler firing during teardown
    this.fireT += dt
    for (const f of this.flames) {
      const wobble = Math.sin(this.fireT * f.rate + f.phase)
      const wobble2 = Math.sin(this.fireT * f.rate * 0.7 + f.phase + 1.3)
      // Vertical stretch + subtle horizontal breathe
      const sy = f.baseScale * (1.4 + wobble * 0.35)
      const sxz = f.baseScale * (0.7 + wobble2 * 0.1)
      f.entity.setLocalScale(sxz, sy, sxz)
      // Drift up slightly as the flame "breathes"
      const yOffset = (wobble + 1) * 0.08
      f.entity.setLocalPosition(
        f.baseX + wobble2 * 0.02,
        f.baseY + f.baseScale * 0.6 + yOffset,
        f.baseZ + wobble * 0.02,
      )
    }
    // Flicker the omni light in sync with the dominant flame.
    // Guard: entity.parent is null once removed from scene graph — the
    // LightComponent.intensity setter reads internal _light which is null by then.
    if (this.fireLight?.entity?.parent) {
      const pulse = Math.sin(this.fireT * 9) * 0.25 + Math.sin(this.fireT * 13.7) * 0.15
      this.fireLight.intensity = 2.2 + pulse
    }
  }

  /**
   * Decorative dark-wood corner post. Purely visual — no collider.
   */
  private createPost(parent: pc.Entity, lx: number, lz: number): void {
    const post = new pc.Entity('PavilionPost')
    post.addComponent('render', { type: 'box' })
    post.setLocalScale(POST_THICKNESS, POST_HEIGHT, POST_THICKNESS)
    post.setLocalPosition(lx, POST_HEIGHT / 2, lz)

    const mat = new pc.StandardMaterial()
    this.materials.push(mat)
    mat.diffuse = new pc.Color(0.35, 0.22, 0.14)   // warm dark wood
    mat.metalness = 0
    mat.gloss = 0.2
    mat.update()
    post.render!.meshInstances[0].material = mat
    post.render!.castShadows = true
    parent.addChild(post)
  }
}
