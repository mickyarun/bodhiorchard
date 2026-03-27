/**
 * Tree3DSystem — BFS growth orchestrator + PlayCanvas renderer.
 * Port of Tree3D's TreeWorld.java growth algorithm.
 *
 * Performance:
 *   - Incremental entity management — each branch gets one entity, created
 *     once on birth and updated in-place. No destroy/recreate cycle.
 *   - Branch materials managed directly (new StandardMaterial, not
 *     MaterialFactory). This avoids ref-count complexity and prevents
 *     mid-frame material.destroy() calls that destabilize the GPU pipeline.
 *   - Static scratch Vec3/Quat in orientAlongDirection + getGrowTipInto —
 *     zero per-frame GC across all active-branch update paths.
 *   - step() uses swap-remove to retire dead branches — no Set or filter alloc.
 *
 * Emissive note: branch materials use emissive = 70% of diffuse against a
 * near-black scene to create a glow effect. This is intentional for this
 * standalone demo and should NOT be replicated in the main garden engine,
 * which uses proper IBL + ACES tone mapping (see ARCHITECTURE.md).
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { Vec3 } from './Vec3'
import { TreeBranch } from './TreeBranch'
import { defaultTrunk, defaultBranch, type TreeRules, type Color3, WORLD_SCALE } from './TreeRules'

const GROW_SPEED = 200 * WORLD_SCALE
const DEFAULT_ROOT_COLOR: Color3 = [180, 180, 180]
const THICKNESS_DIVISOR = 14
const COLLECT_MAX_DEPTH = 30

export class Tree3DSystem {
  private treeRoot: pc.Entity

  private tree: TreeBranch | null = null
  private activeBranches: TreeBranch[] = []
  private trunkRules: TreeRules
  private branchRules: TreeRules
  private goal = new Vec3(0, 1, 0)
  private rootColor: Color3 = DEFAULT_ROOT_COLOR

  // One entity per branch — created once on birth
  private entityMap = new Map<TreeBranch, pc.Entity>()
  // Direct material ownership — no MaterialFactory ref counting
  private matCache  = new Map<string, pc.StandardMaterial>()

  private growing = false

  // Static scratch objects — zero GC in hot update paths
  private static _up      = new pc.Vec3(0, 1, 0)
  private static _target  = new pc.Vec3()
  private static _cross   = new pc.Vec3()
  private static _quat    = new pc.Quat()
  // Scratch Vec3 for getGrowTipInto — avoids 2 allocations per active branch per frame
  private static _growTip = new Vec3(0, 0, 0)

  constructor(app: pc.AppBase, _materials: MaterialFactory) {
    this.trunkRules  = defaultTrunk()
    this.branchRules = defaultBranch()
    this.treeRoot    = new pc.Entity('Tree3D')
    app.root.addChild(this.treeRoot)
  }

  startTree(rootColor: Color3 = DEFAULT_ROOT_COLOR): void {
    this.rootColor = rootColor
    this.clearEntities()
    // Destroy old branch materials AFTER entities are gone — safe, explicit, no ref-count issues
    this.destroyMaterials()
    this.activeBranches = []

    const avgSize = (this.trunkRules.size + this.branchRules.size) / 2
    this.tree = TreeBranch.createRoot(0, 0, 0, (120 / avgSize) * WORLD_SCALE, rootColor)
    this.activeBranches.push(this.tree)
    this.createEntity(this.tree)
    this.growing = true
  }

  reset(): void {
    this.clearEntities()
    this.destroyMaterials()
    this.tree = null
    this.activeBranches = []
    this.growing = false
  }

  /** Per-frame update. Returns true while tree is still growing. */
  update(dt: number): boolean {
    if (!this.growing || this.activeBranches.length === 0) return false

    const newBranches = this.step(GROW_SPEED * dt)
    for (const b of newBranches) this.createEntity(b)
    for (const b of this.activeBranches) this.updateEntity(b)

    if (this.activeBranches.length === 0) this.growing = false
    return this.growing
  }

  isGrowing(): boolean { return this.growing }

  getRootColor(): Color3 { return this.rootColor }

  /** Terminal tip positions for leaf attachment. Call after isGrowing() = false. */
  getTerminalTips(): Array<{ position: pc.Vec3; size: number }> {
    if (!this.tree) return []
    const out: Array<{ position: pc.Vec3; size: number }> = []
    this.collectTerminal(this.tree, out, 0)
    return out
  }

  private collectTerminal(
    branch: TreeBranch,
    out: Array<{ position: pc.Vec3; size: number }>,
    depth: number,
  ): void {
    if (depth > COLLECT_MAX_DEPTH) return
    if (branch.babies.length === 0) {
      const tip = branch.getTip()
      out.push({ position: new pc.Vec3(tip.x, tip.y, tip.z), size: branch.size })
    } else {
      for (const baby of branch.babies) this.collectTerminal(baby, out, depth + 1)
    }
  }

  /**
   * Swap-remove dead branches — avoids Set allocation and array filter/spread on every frame.
   * Dead branches are swapped to the end and the array is truncated in place.
   */
  private step(growAmount: number): TreeBranch[] {
    const newBranches: TreeBranch[] = []

    let i = 0
    while (i < this.activeBranches.length) {
      const branch = this.activeBranches[i]
      if (branch.grow(growAmount)) {
        this.updateEntity(branch)
        const babyTrunk  = branch.makeBaby(this.trunkRules, this.goal)
        const babyBranch = branch.makeBaby(this.branchRules, this.goal)
        if (babyTrunk)  newBranches.push(babyTrunk)
        if (babyBranch) newBranches.push(babyBranch)
        // Swap-remove: replace dead slot with last element, do not advance i
        this.activeBranches[i] = this.activeBranches[this.activeBranches.length - 1]
        this.activeBranches.length--
      } else {
        i++
      }
    }

    this.activeBranches.push(...newBranches)
    return newBranches
  }

  private createEntity(branch: TreeBranch): void {
    const entity = new pc.Entity('B')
    entity.addComponent('render', { type: 'cylinder' })
    entity.render!.meshInstances[0].material = this.getMaterial(branch.color)
    entity.setPosition(branch.root.x, branch.root.y, branch.root.z)
    entity.setLocalScale(0.001, 0.001, 0.001)
    this.treeRoot.addChild(entity)
    this.entityMap.set(branch, entity)
  }

  private updateEntity(branch: TreeBranch): void {
    const entity = this.entityMap.get(branch)
    if (!entity || branch.growthSize <= 0) return

    // Zero-alloc: write grow tip directly into static scratch Vec3
    const growTip = Tree3DSystem._growTip
    branch.getGrowTipInto(growTip)
    const dirLen = growTip.length()
    if (dirLen < 0.01) return

    const thickness = Math.max(branch.size / THICKNESS_DIVISOR, 0.003)
    entity.setLocalScale(thickness * 2, dirLen, thickness * 2)
    entity.setPosition(
      branch.root.x + growTip.x / 2,
      branch.root.y + growTip.y / 2,
      branch.root.z + growTip.z / 2,
    )
    this.orientAlongDirection(entity, growTip)
  }

  /** Zero-allocation orientation: static scratch objects, no per-frame heap pressure. */
  private orientAlongDirection(entity: pc.Entity, dir: Vec3): void {
    const up     = Tree3DSystem._up
    const target = Tree3DSystem._target.set(dir.x, dir.y, dir.z)
    target.normalize()

    const dot = up.dot(target)
    if (dot > 0.9999) return
    if (dot < -0.9999) { entity.setEulerAngles(180, 0, 0); return }

    const cross = Tree3DSystem._cross.cross(up, target)
    const quat  = Tree3DSystem._quat.set(cross.x, cross.y, cross.z, 1 + dot)
    const len   = Math.sqrt(quat.x**2 + quat.y**2 + quat.z**2 + quat.w**2)
    quat.x /= len; quat.y /= len; quat.z /= len; quat.w /= len
    entity.setRotation(quat)
  }

  /** Direct StandardMaterial — bypasses MaterialFactory to avoid ref-count issues. */
  private getMaterial(color: Color3): pc.StandardMaterial {
    const key = `${color[0]}_${color[1]}_${color[2]}`
    let mat = this.matCache.get(key)
    if (!mat) {
      const r = color[0] / 255, g = color[1] / 255, b = color[2] / 255
      mat = new pc.StandardMaterial()
      mat.diffuse   = new pc.Color(r, g, b)
      mat.metalness = 0
      mat.gloss     = 0.3
      mat.emissive  = new pc.Color(r * 0.7, g * 0.7, b * 0.7)
      mat.update()
      this.matCache.set(key, mat)
    }
    return mat
  }

  private clearEntities(): void {
    for (const entity of this.entityMap.values()) entity.destroy()
    this.entityMap.clear()
  }

  private destroyMaterials(): void {
    for (const mat of this.matCache.values()) mat.destroy()
    this.matCache.clear()
  }

  destroy(): void {
    this.clearEntities()
    this.destroyMaterials()
    this.treeRoot.destroy()
  }
}
