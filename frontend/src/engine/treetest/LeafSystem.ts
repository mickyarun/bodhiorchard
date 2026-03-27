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

const MAX_TIPS        = 160    // cap terminal tips — max entities = 160 * 10 = 1600
const LEAVES_PER_TIP  = 10
const LEAF_HEIGHT     = 0.32   // world units — larger leaves for denser canopy appearance
const LEAF_WIDTH      = 0.70   // width/height ratio
const WIND_FREQ_BASE  = 1.3    // Hz
const WIND_AMPLITUDE  = 10     // degrees
const LEAF_SCALE_VARY = 0.50

interface LeafEntry {
  entity: pc.Entity
  basePitch: number
  baseYaw: number
  baseRoll: number
  phase: number
  freq: number
}

export class LeafSystem {
  private app: pc.AppBase
  private materials: MaterialFactory
  private leafRoot: pc.Entity
  private leaves: LeafEntry[] = []
  private leafMesh: pc.Mesh | null = null
  private patchedMaterials = new Set<string>()
  private time = 0

  constructor(app: pc.AppBase, materials: MaterialFactory) {
    this.app = app
    this.materials = materials
    this.leafRoot = new pc.Entity('LeafRoot')
    app.root.addChild(this.leafRoot)
  }

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
    if (!this.leafMesh) this.leafMesh = this.buildLeafMesh()

    const sampled = tips.length <= MAX_TIPS ? tips : reservoirSample(tips, MAX_TIPS)

    // Fetch material ONCE — avoids inflating MaterialFactory refCount once per leaf
    const mat = this.getLeafMaterial(treeColor)

    for (const tip of sampled) {
      for (let i = 0; i < LEAVES_PER_TIP; i++) {
        this.spawnLeaf(tip.position, tip.size, mat)
      }
    }
  }

  /** Per-frame wind sway. */
  update(dt: number): void {
    this.time += dt
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

  clear(): void {
    for (const leaf of this.leaves) leaf.entity.destroy()
    this.leaves = []
    // Destroy mesh GPU buffers on each clear — prevents stale vertexBuffer refs
    // on the next spawnLeaves() when the shadow renderer tries to draw them.
    this.leafMesh?.destroy()
    this.leafMesh = null
  }

  destroy(): void {
    this.clear()
    this.leafMesh?.destroy()
    this.leafMesh = null
    this.leafRoot.destroy()
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  private spawnLeaf(pos: pc.Vec3, branchSize: number, mat: pc.StandardMaterial): void {
    const scale = LEAF_HEIGHT * (0.75 + Math.random() * LEAF_SCALE_VARY)
    const mi    = new pc.MeshInstance(this.leafMesh!, mat)

    const entity = new pc.Entity('Leaf')
    entity.addComponent('render', { meshInstances: [mi] })
    // Disable shadow casting — leaves don't need to cast shadows and removing
    // them from the shadow pass is the biggest single performance saving.
    entity.render!.castShadows = false

    const pitch = 30 + Math.random() * 45
    const yaw   = Math.random() * 360
    const roll  = (Math.random() - 0.5) * 30

    const scatter = branchSize * 0.65
    entity.setPosition(
      pos.x + (Math.random() - 0.5) * scatter,
      pos.y + (Math.random() - 0.5) * scatter,
      pos.z + (Math.random() - 0.5) * scatter,
    )
    entity.setEulerAngles(pitch, yaw, roll)
    entity.setLocalScale(scale, scale, scale)

    this.leafRoot.addChild(entity)
    this.leaves.push({
      entity,
      basePitch: pitch, baseYaw: yaw, baseRoll: roll,
      phase: Math.random() * Math.PI * 2,
      freq:  WIND_FREQ_BASE * (0.65 + Math.random() * 0.7),
    })
  }

  /**
   * Lance/teardrop leaf mesh — 9 vertices (8 outer + center fan pivot), 8 triangles.
   * Slight z-curve so the leaf isn't perfectly flat.
   *
   * Uses pc.createMesh() — the v2 recommended utility — which guarantees
   * SEMANTIC_POSITION at attribute location 0, required by the shadow renderer.
   */
  private buildLeafMesh(): pc.Mesh {
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
    return pc.Mesh.fromGeometry(this.app.graphicsDevice, geometry)
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
