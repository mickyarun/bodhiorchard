/**
 * Tree3DSystem — BFS growth orchestrator + PlayCanvas renderer.
 * Port of Tree3D's TreeWorld.java growth algorithm.
 *
 * Each branch is rendered as a PlayCanvas cylinder entity.
 * Growth happens per-frame via step() which advances the BFS wavefront.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { Vec3 } from './Vec3'
import { TreeBranch } from './TreeBranch'
import { defaultTrunk, defaultBranch, type TreeRules, type Color3, WORLD_SCALE } from './TreeRules'

const GROW_SPEED = 200 * WORLD_SCALE  // ~3 world units/sec
const ROOT_COLOR: Color3 = [180, 180, 180]
const THICKNESS_DIVISOR = 14   // branch radius = size / this (Java: line width = size/7)

export class Tree3DSystem {
  private materials: MaterialFactory
  private treeRoot: pc.Entity

  private tree: TreeBranch | null = null
  private activeBranches: TreeBranch[] = []
  private rootSize = 0
  private trunkRules: TreeRules
  private branchRules: TreeRules
  private goal = new Vec3(0, 1, 0) // grow upward (+Y in PlayCanvas)

  // PlayCanvas entities for rendering
  private branchEntities: pc.Entity[] = []
  private materialCache = new Map<string, pc.StandardMaterial>()

  private growing = false

  constructor(app: pc.AppBase, materials: MaterialFactory) {
    this.materials = materials
    this.trunkRules = defaultTrunk()
    this.branchRules = defaultBranch()
    this.treeRoot = new pc.Entity('Tree3D')
    app.root.addChild(this.treeRoot)
  }

  /** Start growing a new tree. */
  startTree(): void {
    this.destroyEntities()
    this.activeBranches = []

    const avgSize = (this.trunkRules.size + this.branchRules.size) / 2
    this.rootSize = (120 / avgSize) * WORLD_SCALE
    // Root at ground level, growing upward
    this.tree = new TreeBranch(0, 0, 0, this.rootSize, ROOT_COLOR)
    this.activeBranches.push(this.tree)
    this.growing = true
  }

  /** Reset — destroy everything. */
  reset(): void {
    this.destroyEntities()
    this.tree = null
    this.activeBranches = []
    this.growing = false
  }

  /** Per-frame update. Returns true if tree is still growing. */
  update(dt: number): boolean {
    if (!this.growing || this.activeBranches.length === 0) return false

    const growAmount = GROW_SPEED * dt
    const done = this.step(growAmount)

    // Rebuild visual entities from tree data
    this.rebuildEntities()

    if (!done) {
      this.growing = false
    }
    return this.growing
  }

  isGrowing(): boolean { return this.growing }

  /** One step of the BFS growth algorithm — exact port of TreeWorld.step(). */
  private step(growAmount: number): boolean {
    const newBranches: TreeBranch[] = []
    const deadBranches: TreeBranch[] = []

    for (const branch of this.activeBranches) {
      if (branch.grow(growAmount)) {
        // Branch fully grown — spawn two children
        const babyTrunk = branch.makeBaby(this.trunkRules, this.goal)
        const babyBranch = branch.makeBaby(this.branchRules, this.goal)

        if (babyTrunk) newBranches.push(babyTrunk)
        if (babyBranch) newBranches.push(babyBranch)
        deadBranches.push(branch)
      }
    }

    // Remove finished, add new
    this.activeBranches = this.activeBranches.filter(b => !deadBranches.includes(b))
    this.activeBranches.push(...newBranches)

    return this.activeBranches.length > 0
  }

  /** Traverse tree, create/update PlayCanvas cylinder per branch. */
  private rebuildEntities(): void {
    this.destroyEntities()
    if (!this.tree) return
    this.traverseAndBuild(this.tree)
  }

  private traverseAndBuild(branch: TreeBranch): void {
    if (branch.growthSize <= 0) return

    const growTip = branch.getGrowTip()
    const worldTip = branch.root.add(growTip)

    // Midpoint for entity position
    const midX = (branch.root.x + worldTip.x) / 2
    const midY = (branch.root.y + worldTip.y) / 2
    const midZ = (branch.root.z + worldTip.z) / 2

    // Branch direction
    const dirLen = growTip.length()
    if (dirLen < 0.01) return

    // Thickness: Java uses stroke width = size/7, we use radius = size/14
    const thickness = Math.max(branch.size / THICKNESS_DIVISOR, 0.003)

    // Get or create material for this color
    const mat = this.getMaterial(branch.color)

    const entity = new pc.Entity('B')
    entity.addComponent('render', { type: 'cylinder' })
    entity.render!.meshInstances[0].material = mat

    // Scale: diameter × length × diameter
    entity.setLocalScale(thickness * 2, dirLen, thickness * 2)

    // Position at midpoint
    entity.setPosition(midX, midY, midZ)

    // Orient: align cylinder Y-axis with branch direction
    this.orientAlongDirection(entity, growTip)

    this.treeRoot.addChild(entity)
    this.branchEntities.push(entity)

    // Recurse into children
    for (const baby of branch.babies) {
      this.traverseAndBuild(baby)
    }
  }

  /** Align entity's local Y-axis with the given direction vector. */
  private orientAlongDirection(entity: pc.Entity, dir: Vec3): void {
    // Default cylinder axis is Y. We need to rotate Y-axis to align with dir.
    const up = new pc.Vec3(0, 1, 0)
    const target = new pc.Vec3(dir.x, dir.y, dir.z)
    target.normalize()

    // Quaternion from Y-axis to target direction
    const dot = up.dot(target)
    if (dot > 0.9999) return // already aligned
    if (dot < -0.9999) {
      // Opposite — rotate 180° around X
      entity.setEulerAngles(180, 0, 0)
      return
    }

    const cross = new pc.Vec3()
    cross.cross(up, target)
    const quat = new pc.Quat(cross.x, cross.y, cross.z, 1 + dot)
    const len = Math.sqrt(quat.x * quat.x + quat.y * quat.y + quat.z * quat.z + quat.w * quat.w)
    quat.x /= len; quat.y /= len; quat.z /= len; quat.w /= len
    entity.setRotation(quat)
  }

  /** Get/create PBR material for the given RGB color. */
  private getMaterial(color: Color3): pc.StandardMaterial {
    const key = `${color[0]}_${color[1]}_${color[2]}`
    let mat = this.materialCache.get(key)
    if (mat) return mat

    mat = this.materials.getColor(
      `tree_${key}`,
      color[0] / 255,
      color[1] / 255,
      color[2] / 255,
      { metalness: 0, gloss: 0.2 },
    )
    this.materialCache.set(key, mat)
    return mat
  }

  private destroyEntities(): void {
    for (const e of this.branchEntities) e.destroy()
    this.branchEntities = []
  }

  destroy(): void {
    this.destroyEntities()
    for (const [key] of this.materialCache) {
      this.materials.release(`tree_${key}`)
    }
    this.materialCache.clear()
    this.treeRoot.destroy()
  }
}
