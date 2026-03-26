/**
 * Tree3DSystem — BFS growth orchestrator + PlayCanvas renderer.
 * Supports multiple trees (forest) with different species presets.
 *
 * Each branch is rendered as a PlayCanvas cylinder entity.
 * Growth happens per-frame via step() which advances the BFS wavefront.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { Vec3 } from './Vec3'
import { TreeBranch } from './TreeBranch'
import {
  defaultTrunk, defaultBranch,
  type TreeRules, type Color3,
  WORLD_SCALE, PRESETS,
} from './TreeRules'

const GROW_SPEED = 200 * WORLD_SCALE  // ~3 world units/sec
const THICKNESS_DIVISOR = 14
const ROOT_COLOR: Color3 = [180, 180, 180]

/** A single tree instance with its position and rules. */
interface TreeInstance {
  tree: TreeBranch
  activeBranches: TreeBranch[]
  trunkRules: TreeRules
  branchRules: TreeRules
  goal: Vec3
  rootSize: number
  offsetX: number
  offsetZ: number
}

export class Tree3DSystem {
  private materials: MaterialFactory
  private treeRoot: pc.Entity
  private trees: TreeInstance[] = []
  private branchEntities: pc.Entity[] = []
  private materialCache = new Map<string, pc.StandardMaterial>()
  private growing = false

  constructor(app: pc.AppBase, materials: MaterialFactory) {
    this.materials = materials
    this.treeRoot = new pc.Entity('Tree3D')
    app.root.addChild(this.treeRoot)
  }

  /** Start growing a single tree at origin with default rules. */
  startTree(): void {
    this.reset()
    this.addTree(0, 0, defaultTrunk(), defaultBranch(), ROOT_COLOR, 1.0)
    this.growing = true
  }

  /** Start a forest of multiple trees with varied presets. */
  startForest(count: number = 5): void {
    this.reset()
    const positions = this.computePositions(count, 6)
    for (let i = 0; i < count; i++) {
      const presetFn = PRESETS[i % PRESETS.length]
      const preset = presetFn()
      this.addTree(
        positions[i].x, positions[i].z,
        preset.trunk, preset.branch,
        preset.rootColor, preset.sizeMultiplier,
      )
    }
    this.growing = true
  }

  /** Add a single tree instance at the given position. */
  private addTree(
    x: number, z: number,
    trunkRules: TreeRules, branchRules: TreeRules,
    rootColor: Color3, sizeMultiplier: number,
  ): void {
    const avgSize = (trunkRules.size + branchRules.size) / 2
    const rootSize = (120 / avgSize) * WORLD_SCALE * sizeMultiplier
    const tree = new TreeBranch(x, 0, z, rootSize, rootColor)
    this.trees.push({
      tree,
      activeBranches: [tree],
      trunkRules,
      branchRules,
      goal: new Vec3(0, 1, 0),
      rootSize,
      offsetX: x,
      offsetZ: z,
    })
  }

  /** Compute non-overlapping positions in a circle around origin. */
  private computePositions(count: number, spacing: number): Array<{ x: number; z: number }> {
    if (count === 1) return [{ x: 0, z: 0 }]
    const positions: Array<{ x: number; z: number }> = []
    // Center tree
    positions.push({ x: 0, z: 0 })
    // Ring of remaining trees
    const ringCount = count - 1
    for (let i = 0; i < ringCount; i++) {
      const angle = (i / ringCount) * Math.PI * 2
      positions.push({
        x: Math.cos(angle) * spacing,
        z: Math.sin(angle) * spacing,
      })
    }
    return positions
  }

  reset(): void {
    this.destroyEntities()
    this.trees = []
    this.growing = false
  }

  update(dt: number): boolean {
    if (!this.growing || this.trees.length === 0) return false

    const growAmount = GROW_SPEED * dt
    let anyActive = false

    for (const inst of this.trees) {
      if (inst.activeBranches.length > 0) {
        anyActive = this.stepTree(inst, growAmount) || anyActive
      }
    }

    this.rebuildEntities()

    if (!anyActive) this.growing = false
    return this.growing
  }

  isGrowing(): boolean { return this.growing }

  /** One BFS step for a single tree instance. */
  private stepTree(inst: TreeInstance, growAmount: number): boolean {
    const newBranches: TreeBranch[] = []
    const deadBranches: TreeBranch[] = []

    for (const branch of inst.activeBranches) {
      if (branch.grow(growAmount)) {
        const babyTrunk = branch.makeBaby(inst.trunkRules, inst.goal)
        const babyBranch = branch.makeBaby(inst.branchRules, inst.goal)
        if (babyTrunk) newBranches.push(babyTrunk)
        if (babyBranch) newBranches.push(babyBranch)
        deadBranches.push(branch)
      }
    }

    inst.activeBranches = inst.activeBranches.filter(b => !deadBranches.includes(b))
    inst.activeBranches.push(...newBranches)
    return inst.activeBranches.length > 0
  }

  private rebuildEntities(): void {
    this.destroyEntities()
    for (const inst of this.trees) {
      this.traverseAndBuild(inst.tree)
    }
  }

  private traverseAndBuild(branch: TreeBranch): void {
    if (branch.growthSize <= 0) return

    const growTip = branch.getGrowTip()
    const worldTip = branch.root.add(growTip)
    const dirLen = growTip.length()
    if (dirLen < 0.01) return

    const thickness = Math.max(branch.size / THICKNESS_DIVISOR, 0.003)
    const mat = this.getMaterial(branch.color)

    const entity = new pc.Entity('B')
    entity.addComponent('render', { type: 'cylinder' })
    entity.render!.meshInstances[0].material = mat
    entity.setLocalScale(thickness * 2, dirLen, thickness * 2)
    entity.setPosition(
      (branch.root.x + worldTip.x) / 2,
      (branch.root.y + worldTip.y) / 2,
      (branch.root.z + worldTip.z) / 2,
    )
    this.orientAlongDirection(entity, growTip)
    this.treeRoot.addChild(entity)
    this.branchEntities.push(entity)

    for (const baby of branch.babies) {
      this.traverseAndBuild(baby)
    }
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
    const len = Math.sqrt(quat.x * quat.x + quat.y * quat.y + quat.z * quat.z + quat.w * quat.w)
    quat.x /= len; quat.y /= len; quat.z /= len; quat.w /= len
    entity.setRotation(quat)
  }

  private getMaterial(color: Color3): pc.StandardMaterial {
    const key = `${color[0]}_${color[1]}_${color[2]}`
    let mat = this.materialCache.get(key)
    if (mat) return mat
    mat = this.materials.getColor(
      `tree_${key}`, color[0] / 255, color[1] / 255, color[2] / 255,
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
