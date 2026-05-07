// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * LeafSystem — natural procedural leaf clusters at branch tips.
 *
 * Geometry: lance/teardrop mesh (9 verts, 8 tris). Slight z-curve for 3D volume.
 *
 * Performance design:
 *   - MAX_TIPS cap + reservoir sampling → at most MAX_TIPS * LEAVES_PER_TIP entities
 *   - Material is fetched ONCE before the spawn loop, not once per leaf.
 *     This avoids inflating MaterialFactory refCount per leaf (which would
 *     make the material un-evictable and leak memory across tree runs).
 *   - patchedMaterials set prevents redundant mat.update() on cache hits.
 *   - Leaf color uses the SELECTED root color, not tip color (tips are near-
 *     white due to wiggleColor drift and would make all leaves look the same).
 *
 * Wind: per-leaf phase-offset sin oscillation — each leaf sways independently.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { Color3 } from './TreeRules'
import type { WindSystem } from './WindSystem'
import type { BakedLeafGroup } from './treeCache'
import { createInstancedEntity, computeInstanceAabb } from './instancing'

const MAX_TIPS        = 160    // cap terminal tips — max entities = 160 * 10 = 1600
const LEAVES_PER_TIP  = 10
const LEAF_HEIGHT     = 0.32   // world units — larger leaves for denser canopy appearance
const LEAF_WIDTH      = 0.70   // width/height ratio
const WIND_FREQ_BASE  = 1.3    // Hz — fallback when no WindSystem connected
const WIND_AMPLITUDE  = 10     // degrees — fallback amplitude
const LEAF_SCALE_VARY = 0.50
/** AABB inflation for baked leaf batches — covers leaf quad extent (~0.7 wide) plus wind sway slack. */
const LEAF_AABB_MARGIN = 1.0

interface LeafEntry {
  entity: pc.Entity
  basePitch: number
  baseYaw: number
  baseRoll: number
  phase: number
  freq: number
  worldX: number
  worldZ: number
}

export class LeafSystem {
  private app: pc.AppBase
  private materials: MaterialFactory
  private leafRoot: pc.Entity
  private leaves: LeafEntry[] = []
  private patchedMaterials = new Set<string>()
  private time = 0
  private windSystem: WindSystem | null = null

  // Tree-color used for the leaf material. Tracked on spawn / restore so
  // bakeInstanced doesn't need it passed in (would diverge from what the
  // per-leaf entities were already spawned with).
  private treeColor: Color3 | null = null

  // Instancing bake: populated by bakeInstanced(). update() short-circuits
  // once the per-leaf entity list is cleared post-bake. Baked GPU resources
  // live until destroy() / clear().
  private bakedEntities: pc.Entity[] = []
  private bakedVertexBuffers: pc.VertexBuffer[] = []

  // Shared lance-leaf mesh, keyed by graphics device so hot-reload / multi-app
  // contexts never hand out a mesh bound to a stale device. All LeafSystem
  // instances on the same device share the same 9-vert geometry — 21 repos
  // used to mean 21 identical GPU uploads.
  private static _leafMeshByDevice = new WeakMap<pc.GraphicsDevice, pc.Mesh>()

  constructor(app: pc.AppBase, materials: MaterialFactory, parent?: pc.Entity) {
    this.app = app
    this.materials = materials
    this.leafRoot = new pc.Entity('LeafRoot')
    ;(parent ?? app.root).addChild(this.leafRoot)
  }

  /** Connect a WindSystem for coherent wind across branches and leaves. */
  setWindSystem(wind: WindSystem): void { this.windSystem = wind }

  /** Root entity owning all live + baked leaf children — used by callers that
   *  want to toggle the whole leaf subtree on/off (e.g. distance-LOD culling). */
  getRoot(): pc.Entity { return this.leafRoot }

  /**
   * Spawn leaf clusters at terminal branch tip positions.
   * treeColor = the SELECTED root color from the UI (not tip color, which is
   * always near-white and makes every tree produce identical-looking leaves).
   */
  spawnLeaves(
    tips: Array<{ position: pc.Vec3; size: number }>,
    treeColor: Color3,
  ): void {
    this.clear()
    this.treeColor = [...treeColor] as Color3

    const sampled = tips.length <= MAX_TIPS ? tips : reservoirSample(tips, MAX_TIPS)

    // Fetch material ONCE — avoids inflating MaterialFactory refCount once per leaf
    const mat = this.getLeafMaterial(treeColor)
    const mesh = this.getLeafMesh()

    for (const tip of sampled) {
      for (let i = 0; i < LEAVES_PER_TIP; i++) {
        this.spawnLeaf(tip.position, tip.size, mat, mesh)
      }
    }
  }

  /** Per-frame wind sway. Uses WindSystem when connected, else standalone sine fallback. */
  update(dt: number): void {
    this.time += dt

    if (this.windSystem) {
      // WindSystem-driven: coherent multi-frequency sway synced with branches
      for (const leaf of this.leaves) {
        const [pitchSway, rollSway] = this.windSystem.getLeafSway(
          leaf.worldX, leaf.worldZ, leaf.phase,
        )
        leaf.entity.setEulerAngles(
          leaf.basePitch + pitchSway,
          leaf.baseYaw,
          leaf.baseRoll + rollSway,
        )
      }
    } else {
      // Standalone fallback — original independent sine sway
      for (const leaf of this.leaves) {
        const sway  = Math.sin(this.time * leaf.freq + leaf.phase)       * WIND_AMPLITUDE
        const sway2 = Math.cos(this.time * leaf.freq * 0.7 + leaf.phase) * WIND_AMPLITUDE * 0.4
        leaf.entity.setEulerAngles(
          leaf.basePitch + sway,
          leaf.baseYaw,
          leaf.baseRoll + sway2,
        )
      }
    }
  }

  /**
   * Collapse every spawned leaf into one hardware-instanced MeshInstance per
   * material (typically just one — each tree uses a single leaf color). Read
   * each leaf's world matrix, pack into an instance VertexBuffer, attach to a
   * single MeshInstance, then destroy the per-leaf entities.
   *
   * After bake this.leaves is empty so update() becomes a no-op. Whole-tree
   * sway still plays via Tree3DSystem.applyWind() rotating treeRoot — leaves
   * parented under that root sway with it; the per-leaf sine jiggle is gone
   * by design (not worth ~33k setEulerAngles calls per frame per garden).
   */
  bakeInstanced(): BakedLeafGroup | null {
    if (this.leaves.length === 0 || !this.treeColor) return null

    // All leaves in a tree share a single material today, so one group is
    // sufficient. Pack every leaf's tree-LOCAL transform into a single
    // Float32Array. Local because leafRoot is parented to the tree's
    // treeRoot — the renderer applies treeRoot.world × matrix at draw time,
    // so storing world matrices here would double-apply the tree's world
    // position and leaves would drift to 2× the tree's offset from origin.
    const flat = new Float32Array(this.leaves.length * 16)
    for (let i = 0; i < this.leaves.length; i++) {
      const lt = this.leaves[i].entity.getLocalTransform()
      flat.set(lt.data, i * 16)
    }

    this.createInstancedLeafEntity(flat, this.leaves.length, this.treeColor)

    for (const leaf of this.leaves) leaf.entity.destroy()
    this.leaves = []

    return { color: [...this.treeColor] as Color3, matrices: flat, count: flat.length / 16 }
  }

  /**
   * Reconstruct the tree's leaf instanced MeshInstance from a cached bake.
   * Skips spawnLeaves + bakeInstanced in favor of directly rebuilding the
   * VertexBuffer and MeshInstance. Called on cache hit.
   */
  loadFromCache(data: BakedLeafGroup): void {
    this.clear()
    if (data.count === 0) return
    this.treeColor = [...data.color] as Color3
    this.createInstancedLeafEntity(data.matrices, data.count, data.color)
  }

  private createInstancedLeafEntity(
    matrices: Float32Array,
    count: number,
    treeColor: Color3,
  ): void {
    const mat = this.getLeafMaterial(treeColor)
    const aabb = computeInstanceAabb(matrices, count, LEAF_AABB_MARGIN)
    const { entity, vb } = createInstancedEntity(
      this.app.graphicsDevice,
      this.getLeafMesh(),
      mat,
      matrices,
      count,
      'BakedLeaves',
      { aabb },
    )
    this.leafRoot.addChild(entity)
    this.bakedEntities.push(entity)
    this.bakedVertexBuffers.push(vb)
  }

  clear(): void {
    // Destroy baked entities + their VBs first. The leaf mesh is shared across
    // all LeafSystem instances on this device (see _leafMeshByDevice) and is
    // owned by the device's lifetime, not this instance — we never destroy it.
    for (const e of this.bakedEntities) e.destroy()
    for (const vb of this.bakedVertexBuffers) vb.destroy()
    this.bakedEntities = []
    this.bakedVertexBuffers = []

    for (const leaf of this.leaves) leaf.entity.destroy()
    this.leaves = []
    this.treeColor = null
  }

  destroy(): void {
    this.clear()
    this.leafRoot.destroy()
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  private spawnLeaf(pos: pc.Vec3, branchSize: number, mat: pc.StandardMaterial, mesh: pc.Mesh): void {
    const scale = LEAF_HEIGHT * (0.75 + Math.random() * LEAF_SCALE_VARY)
    const mi    = new pc.MeshInstance(mesh, mat)

    const entity = new pc.Entity('Leaf')
    entity.addComponent('render', { meshInstances: [mi] })
    // Disable shadow casting — leaves don't need to cast shadows and removing
    // them from the shadow pass is the biggest single performance saving.
    entity.render!.castShadows = false

    const pitch = 30 + Math.random() * 45
    const yaw   = Math.random() * 360
    const roll  = (Math.random() - 0.5) * 30

    const scatter = branchSize * 0.65
    // Local coords — leafRoot is parented to the tree's world-positioned
    // treeRoot in ProceduralTreeSystem, so leaves inherit the tree's
    // world transform via the scene graph rather than baking world coords here.
    entity.setLocalPosition(
      pos.x + (Math.random() - 0.5) * scatter,
      pos.y + (Math.random() - 0.5) * scatter,
      pos.z + (Math.random() - 0.5) * scatter,
    )
    entity.setEulerAngles(pitch, yaw, roll)
    entity.setLocalScale(scale, scale, scale)

    this.leafRoot.addChild(entity)
    const leafPos = entity.getPosition()
    this.leaves.push({
      entity,
      basePitch: pitch, baseYaw: yaw, baseRoll: roll,
      phase: Math.random() * Math.PI * 2,
      freq:  WIND_FREQ_BASE * (0.65 + Math.random() * 0.7),
      worldX: leafPos.x,
      worldZ: leafPos.z,
    })
  }

  /**
   * Lance/teardrop leaf mesh — 9 vertices (8 outer + center fan pivot), 8 triangles.
   * Slight z-curve so the leaf isn't perfectly flat. Cached per graphics device
   * so every LeafSystem on the same device shares one GPU upload — at 21 repos
   * this drops from 21 × 36 bytes = 756B + 21 buffer lifecycles to a single
   * shared mesh bound to the device's own lifetime.
   */
  private getLeafMesh(): pc.Mesh {
    const device = this.app.graphicsDevice
    const cached = LeafSystem._leafMeshByDevice.get(device)
    if (cached) return cached
    const mesh = this.buildLeafMesh(device)
    LeafSystem._leafMeshByDevice.set(device, mesh)
    return mesh
  }

  private buildLeafMesh(device: pc.GraphicsDevice): pc.Mesh {
    const h = 1.0
    const w = LEAF_WIDTH
    const zc = (y: number) => Math.sin(y * Math.PI) * 0.12

    const positions: number[] = [
       0,        0,          0,               // 0 stem
      -w * 0.30, h * 0.20,  zc(0.20),        // 1 lower-left
       w * 0.30, h * 0.20,  zc(0.20),        // 2 lower-right
      -w * 0.50, h * 0.55,  zc(0.55),        // 3 mid-left (widest)
       w * 0.50, h * 0.55,  zc(0.55),        // 4 mid-right (widest)
      -w * 0.25, h * 0.80,  zc(0.80),        // 5 upper-left
       w * 0.25, h * 0.80,  zc(0.80),        // 6 upper-right
       0,        h,          zc(1.0),         // 7 tip
       0,        h * 0.50,  zc(0.50) * 0.8,  // 8 center (fan pivot)
    ]

    // Fan from center (8) around outer ring: stem → lower-left → … → tip → … → stem
    const indices: number[] = [
      8, 0, 1,  8, 1, 3,  8, 3, 5,  8, 5, 7,
      8, 7, 6,  8, 6, 4,  8, 4, 2,  8, 2, 0,
    ]

    const normals: number[] = []
    for (let i = 0; i < positions.length / 3; i++) normals.push(0, 0, 1)

    const uvs: number[] = [
      0.5, 0.0,   0.2, 0.2,   0.8, 0.2,
      0.0, 0.55,  1.0, 0.55,
      0.15, 0.8,  0.85, 0.8,
      0.5, 1.0,   0.5, 0.5,
    ]

    // pc.Mesh.fromGeometry — the v2.17 non-deprecated API. Builds a proper
    // VertexFormat with SEMANTIC_POSITION at location 0, required by the shadow
    // depth shader. Avoids both the deprecated pc.createMesh and the low-level
    // pc.Mesh.setPositions() which had attribute ordering issues.
    const geometry = new pc.Geometry()
    geometry.positions = positions
    geometry.normals   = normals
    geometry.uvs       = uvs
    geometry.indices   = indices
    return pc.Mesh.fromGeometry(device, geometry)
  }

  /**
   * Two-sided emissive leaf material keyed on the selected tree color.
   * Blends tree color (30%) with natural leaf green (70%) so leaves shift
   * hue with the selected palette while staying recognizably green.
   * cull/twoSidedLighting are patched once per unique key (not on cache hits).
   */
  private getLeafMaterial(treeColor: Color3): pc.StandardMaterial {
    const lr = Math.round(treeColor[0] * 0.3 +  60 * 0.7)
    const lg = Math.round(treeColor[1] * 0.3 + 180 * 0.7)
    const lb = Math.round(treeColor[2] * 0.3 +  50 * 0.7)
    const r = lr / 255, g = lg / 255, b = lb / 255
    const key = `leaf_${lr}_${lg}_${lb}`

    const mat = this.materials.getColor(key, r, g, b, {
      metalness: 0,
      gloss: 0.1,
      emissive: [r * 0.65, g * 0.65, b * 0.65],
    })

    // Patch two-sided properties once — safe since mat object is reused from cache
    if (!this.patchedMaterials.has(key)) {
      mat.cull = pc.CULLFACE_NONE
      mat.twoSidedLighting = true
      mat.update()
      this.patchedMaterials.add(key)
    }
    return mat
  }
}

/** Reservoir sampling — O(n) uniform random sample without sorting. */
function reservoirSample<T>(arr: T[], k: number): T[] {
  const result = arr.slice(0, k)
  for (let i = k; i < arr.length; i++) {
    const j = Math.floor(Math.random() * (i + 1))
    if (j < k) result[j] = arr[i]
  }
  return result
}
