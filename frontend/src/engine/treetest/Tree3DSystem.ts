/**
 * Tree3DSystem — BFS growth orchestrator + PlayCanvas renderer.
 * Port of Tree3D's TreeWorld.java growth algorithm.
 *
 * Performance: incremental entity management — each branch gets one entity,
 * created on birth and updated in-place while growing. No destroy/recreate cycle.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { Vec3 } from './Vec3'
import { TreeBranch } from './TreeBranch'
import { defaultTrunk, defaultBranch, type TreeRules, type Color3, WORLD_SCALE } from './TreeRules'

const GROW_SPEED = 200 * WORLD_SCALE    // ~3 world units/sec
const ROOT_COLOR: Color3 = [180, 180, 180]
const THICKNESS_DIVISOR = 14            // branch radius = size / 14

export class Tree3DSystem {
  private materials: MaterialFactory
  private treeRoot: pc.Entity

  private tree: TreeBranch | null = null
  private activeBranches: TreeBranch[] = []
  private trunkRules: TreeRules
  private branchRules: TreeRules
  private goal = new Vec3(0, 1, 0)

  // One entity per branch — created once on birth, updated in-place while growing
  private entityMap = new Map<TreeBranch, pc.Entity>()
  private materialCache = new Map<string, pc.StandardMaterial>()

  private growing = false

  constructor(app: pc.AppBase, materials: MaterialFactory) {
    this.materials = materials
    this.trunkRules = defaultTrunk()
    this.branchRules = defaultBranch()
    this.treeRoot = new pc.Entity('Tree3D')
    app.root.addChild(this.treeRoot)
  }

  startTree(): void {
    this.clearEntities()
    this.activeBranches = []

    const avgSize = (this.trunkRules.size + this.branchRules.size) / 2
    this.tree = new TreeBranch(0, 0, 0, (120 / avgSize) * WORLD_SCALE, ROOT_COLOR)
    this.activeBranches.push(this.tree)
    this.createEntity(this.tree)
    this.growing = true
  }

  reset(): void {
    this.clearEntities()
    this.tree = null
    this.activeBranches = []
    this.growing = false
  }

  /** Per-frame update. Returns true while tree is still growing. */
  update(dt: number): boolean {
    if (!this.growing || this.activeBranches.length === 0) return false

    const newBranches = this.step(GROW_SPEED * dt)

    // Create entities for newly-born branches (once per branch)
    for (const b of newBranches) this.createEntity(b)

    // Update transforms only for currently-growing branches
    for (const b of this.activeBranches) this.updateEntity(b)

    if (this.activeBranches.length === 0) this.growing = false
    return this.growing
  }

  isGrowing(): boolean { return this.growing }

  /** One BFS step — returns newly-born branches. Port of TreeWorld.step(). */
  private step(growAmount: number): TreeBranch[] {
    const newBranches: TreeBranch[] = []
    const dead = new Set<TreeBranch>()

    for (const branch of this.activeBranches) {
      if (branch.grow(growAmount)) {
        const babyTrunk = branch.makeBaby(this.trunkRules, this.goal)
        const babyBranch = branch.makeBaby(this.branchRules, this.goal)
        if (babyTrunk) newBranches.push(babyTrunk)
        if (babyBranch) newBranches.push(babyBranch)
        dead.add(branch)
      }
    }

    // O(n) removal using Set instead of O(n²) filter+includes
    this.activeBranches = this.activeBranches.filter(b => !dead.has(b))
    this.activeBranches.push(...newBranches)
    return newBranches
  }

  /** Create a PlayCanvas entity for a branch. Called once per branch on birth. */
  private createEntity(branch: TreeBranch): void {
    const entity = new pc.Entity('B')
    entity.addComponent('render', { type: 'cylinder' })
    entity.render!.meshInstances[0].material = this.getMaterial(branch.color)
    // Park at branch root, invisible — updateEntity will size/orient it as it grows
    entity.setPosition(branch.root.x, branch.root.y, branch.root.z)
    entity.setLocalScale(0.001, 0.001, 0.001)
    this.treeRoot.addChild(entity)
    this.entityMap.set(branch, entity)
  }

  /** Update the transform of an existing entity to match current growth state. */
  private updateEntity(branch: TreeBranch): void {
    const entity = this.entityMap.get(branch)
    if (!entity || branch.growthSize <= 0) return

    const growTip = branch.getGrowTip()
    const dirLen = growTip.length()
    if (dirLen < 0.01) return

    const worldTip = branch.root.add(growTip)
    const thickness = Math.max(branch.size / THICKNESS_DIVISOR, 0.003)

    entity.setLocalScale(thickness * 2, dirLen, thickness * 2)
    entity.setPosition(
      (branch.root.x + worldTip.x) / 2,
      (branch.root.y + worldTip.y) / 2,
      (branch.root.z + worldTip.z) / 2,
    )
    this.orientAlongDirection(entity, growTip)
  }

  private orientAlongDirection(entity: pc.Entity, dir: Vec3): void {
    const up = new pc.Vec3(0, 1, 0)
    const target = new pc.Vec3(dir.x, dir.y, dir.z)
    target.normalize()

    const dot = up.dot(target)
    if (dot > 0.9999) return
    if (dot < -0.9999) { entity.setEulerAngles(180, 0, 0); return }

    const cross = new pc.Vec3()
    cross.cross(up, target)
    const quat = new pc.Quat(cross.x, cross.y, cross.z, 1 + dot)
    const len = Math.sqrt(quat.x**2 + quat.y**2 + quat.z**2 + quat.w**2)
    quat.x /= len; quat.y /= len; quat.z /= len; quat.w /= len
    entity.setRotation(quat)
  }

  private getMaterial(color: Color3): pc.StandardMaterial {
    const key = `${color[0]}_${color[1]}_${color[2]}`
    let mat = this.materialCache.get(key)
    if (!mat) {
      mat = this.materials.getColor(
        `tree_${key}`, color[0] / 255, color[1] / 255, color[2] / 255,
        { metalness: 0, gloss: 0.2 },
      )
      this.materialCache.set(key, mat)
    }
    return mat
  }

  private clearEntities(): void {
    for (const entity of this.entityMap.values()) entity.destroy()
    this.entityMap.clear()
  }

  destroy(): void {
    this.clearEntities()
    for (const [key] of this.materialCache) this.materials.release(`tree_${key}`)
    this.materialCache.clear()
    this.treeRoot.destroy()
  }
}
