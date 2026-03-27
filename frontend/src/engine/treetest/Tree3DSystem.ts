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
 *   - For N>16 features: offTrunkRules uses branchRules params (size=0.7, minSize=0.15),
 *     bounding feature sub-tree depth to ~8 levels and total entities to ~64K at N=250.
 *
 * Emissive note: branch materials use emissive = 70% of diffuse against a
 * near-black scene to create a glow effect. This is intentional for this
 * standalone demo and should NOT be replicated in the main garden engine,
 * which uses proper IBL + ACES tone mapping (see ARCHITECTURE.md).
 */
import * as pc from 'playcanvas'
import { Vec3 } from './Vec3'
import { TreeBranch } from './TreeBranch'
import { defaultTrunk, defaultBranch, type TreeRules, type Color3, WORLD_SCALE } from './TreeRules'

const GROW_SPEED             = 200 * WORLD_SCALE
const DEFAULT_ROOT_COLOR: Color3 = [180, 180, 180]
const THICKNESS_DIVISOR   = 14
const MIN_THICKNESS        = 0.003  // world units — prevents hairline artifacts on tiny branches
const COLLECT_MAX_DEPTH   = 30
const DEFAULT_LEVELS      = 16

export class Tree3DSystem {
  private treeRoot: pc.Entity

  private tree: TreeBranch | null = null
  private activeBranches: TreeBranch[] = []
  private trunkRules: TreeRules
  private branchRules: TreeRules
  // Rules for off-trunk branches (feature sub-trees) — reset per startTree().
  // For N>16, copied from branchRules so sub-trees stop at ~3 levels instead of blowing up.
  private offTrunkRules: TreeRules = defaultTrunk()
  private goal = new Vec3(0, 1, 0)
  private rootColor: Color3 = DEFAULT_ROOT_COLOR

  // Growth speed, scaled by √(N/16) for large trees so animation stays snappy
  private growSpeed = GROW_SPEED

  // One entity per branch — created once on birth
  private entityMap = new Map<TreeBranch, pc.Entity>()
  // Direct material ownership — no MaterialFactory ref counting
  private matCache  = new Map<string, pc.StandardMaterial>()

  private growing = false

  // Feature data — primary trunk-side branches get status colors + titles
  private featureData:          Array<{ color: Color3; title: string; status: string }> = []
  private featureBranchCount    = 0
  private trunkChain            = new Set<TreeBranch>()
  // Stores primary branch nodes for post-growth entity traversal (hover hit-testing)
  private featurePrimaryBranches: Array<{ branch: TreeBranch; title: string; status: string }> = []
  // Entity → feature lookup built after growth completes
  private featureEntityMap      = new Map<pc.Entity, { title: string; status: string }>()

  // Static scratch objects — zero GC in hot update paths. Never mutate _up — it is a shared constant.
  private static readonly _up      = new pc.Vec3(0, 1, 0)
  private static readonly _target  = new pc.Vec3()
  private static readonly _cross   = new pc.Vec3()
  private static readonly _quat    = new pc.Quat()
  // Scratch Vec3 for getGrowTipInto — avoids 2 allocations per active branch per frame
  private static readonly _growTip = new Vec3(0, 0, 0)

  // Reusable buffer for new branches emitted by step() — avoids a fresh [] allocation every frame
  private readonly _newBranchBuffer: TreeBranch[] = []

  // When false: no emissive component (for use in the main garden engine with PBR lighting)
  private readonly useEmissive: boolean

  constructor(app: pc.AppBase, options?: { useEmissive?: boolean }) {
    this.useEmissive = options?.useEmissive ?? true
    this.trunkRules  = defaultTrunk()
    this.branchRules = defaultBranch()
    this.treeRoot    = new pc.Entity('Tree3D')
    app.root.addChild(this.treeRoot)
  }

  /** Set feature data — primary trunk-side branches will be colored and labeled in order. */
  setFeatures(features: Array<{ color: Color3; title: string; status: string }>): void {
    this.featureData = features
  }

  /**
   * Begin growing a new tree.
   * @param rootColor - trunk color (0-255 RGB)
   * @param worldX/Y/Z - world-space position of the root (default 0,0,0 for standalone demo)
   */
  startTree(rootColor: Color3 = DEFAULT_ROOT_COLOR, worldX = 0, worldY = 0, worldZ = 0): void {
    this.rootColor = rootColor
    this.clearEntities()
    // Destroy old branch materials AFTER entities are gone — safe, explicit, no ref-count issues
    this.destroyMaterials()
    this.activeBranches = []

    // Always reset rules before scaling — prevents stale state on regrow
    this.trunkRules    = defaultTrunk()
    this.branchRules   = defaultBranch()
    this.offTrunkRules = defaultTrunk()

    const rootSize = this.scaleRulesForFeatureCount(this.featureData.length)

    this.tree = TreeBranch.createRoot(worldX, worldY, worldZ, rootSize, rootColor)
    this.activeBranches.push(this.tree)
    this.createEntity(this.tree)
    this.growing = true

    // Reset trunk-chain tracking for this growth run
    this.trunkChain.clear()
    this.trunkChain.add(this.tree)
    this.featureBranchCount = 0
    this.featurePrimaryBranches = []
    this.featureEntityMap.clear()
  }

  reset(): void {
    this.clearEntities()
    this.destroyMaterials()
    this.tree = null
    this.activeBranches = []
    this.growing = false
    this.trunkChain.clear()
    this.featureBranchCount = 0
    this.featurePrimaryBranches = []
    this.featureEntityMap.clear()
  }

  /** Per-frame update. Returns true while tree is still growing. */
  update(dt: number): boolean {
    if (!this.growing || this.activeBranches.length === 0) return false

    const newBranches = this.step(this.growSpeed * dt)
    for (const b of newBranches) this.createEntity(b)
    for (const b of this.activeBranches) this.updateEntity(b)

    if (this.activeBranches.length === 0) this.growing = false
    return this.growing
  }

  isGrowing(): boolean { return this.growing }

  getRootColor(): Color3 { return this.rootColor }

  /**
   * Build entity → feature map for hover hit-testing.
   * Call once after isGrowing() returns false.
   * Traverses every subtree rooted at a primary feature branch.
   */
  buildFeatureEntityMap(): void {
    this.featureEntityMap.clear()
    for (const fp of this.featurePrimaryBranches) {
      this.collectSubtreeEntities(fp.branch, fp.title, fp.status, 0)
    }
  }

  /** Returns the entity→feature lookup built by buildFeatureEntityMap(). */
  getFeatureEntityMap(): ReadonlyMap<pc.Entity, { title: string; status: string }> {
    return this.featureEntityMap
  }

  /** Terminal tip positions for leaf attachment. Call after isGrowing() = false. */
  getTerminalTips(): Array<{ position: pc.Vec3; size: number }> {
    if (!this.tree) return []
    const out: Array<{ position: pc.Vec3; size: number }> = []
    this.collectTerminal(this.tree, out, 0)
    return out
  }

  // ─── Rule Scaling ────────────────────────────────────────────────────────────

  /**
   * Compute rootSize and adjust rules to support N feature branches.
   * For N > DEFAULT_LEVELS (16): scales trunk height, tightens offTrunkRules so
   * feature sub-trees stay bounded, and increases growSpeed so large trees animate snappily.
   * Returns rootSize for the trunk root node.
   *
   * Entity count with offTrunkRules=branchRules (no size cap needed):
   *   N=50:  sub-tree depth 7 → 128 entities/feature × 50  =  6,400 ✅
   *   N=250: sub-tree depth 8 → 256 entities/feature × 250 = 64,000 ✅
   */
  private scaleRulesForFeatureCount(N: number): number {
    const shrinkRate  = this.trunkRules.size                          // 0.8
    const avgSize     = (shrinkRate + this.branchRules.size) / 2     // 0.75
    const defaultRoot = (120 / avgSize) * WORLD_SCALE                // 2.4

    if (N <= DEFAULT_LEVELS) {
      this.growSpeed = GROW_SPEED
      return defaultRoot
    }

    // Trunk height scales as N^0.25 — subtle but visible from 16 → 250 features
    const defaultHeight = defaultRoot
                        * (1 - Math.pow(shrinkRate, DEFAULT_LEVELS))
                        / (1 - shrinkRate)                            // ≈ 11.6 units
    const targetHeight  = defaultHeight * Math.pow(N / DEFAULT_LEVELS, 0.25)
    const shrinkN       = Math.pow(shrinkRate, N)
    const rootSize      = targetHeight * (1 - shrinkRate)
                        / Math.max(1 - shrinkN, 1e-10)

    // Tiny minSize so trunk grows N levels naturally; keepTrunk=false in step() is the real cap
    this.trunkRules.minSize = rootSize * shrinkN * 0.5

    // Off-trunk branches (feature sub-trees) use trunk growth angles (angle=0, whorl=120°)
    // so they extend naturally outward — NOT branchRules angle (51°) which would cause tight curls.
    // Only override size/minSize from branchRules to bound sub-tree depth:
    //   depth = floor(log(S/0.15) / log(1/0.7)) → ~8 levels for S=3.23 (N=250 level-1 feature)
    this.offTrunkRules = { ...defaultTrunk(), size: this.branchRules.size, minSize: this.branchRules.minSize }

    // Animation speed scales with √(N/16): N=250 → ~4× faster, trunk done in ~2s
    this.growSpeed = GROW_SPEED * Math.sqrt(N / DEFAULT_LEVELS)

    return rootSize
  }

  // ─── Growth Loop ─────────────────────────────────────────────────────────────

  /**
   * Swap-remove dead branches — avoids Set allocation and array filter/spread on every frame.
   * Dead branches are swapped to the end and the array is truncated in place.
   */
  private step(growAmount: number): TreeBranch[] {
    const newBranches = this._newBranchBuffer
    newBranches.length = 0

    let i = 0
    while (i < this.activeBranches.length) {
      const branch = this.activeBranches[i]
      if (branch.grow(growAmount)) {
        this.updateEntity(branch)
        // onTrunk MUST be before makeBaby — trunkRules.minSize may be modified for N>16
        // and must only apply to the actual trunk chain (not feature sub-trees)
        const onTrunk   = this.trunkChain.has(branch)
        const babyTrunk = branch.makeBaby(onTrunk ? this.trunkRules : this.offTrunkRules, this.goal)
        if (babyTrunk && onTrunk) this.trunkChain.add(babyTrunk)

        // Stop growing once all N features have been placed on the trunk chain
        const shouldStop = onTrunk
          && this.featureData.length > 0
          && this.featureBranchCount >= this.featureData.length

        let babyBranch: TreeBranch | null
        if (onTrunk && !shouldStop && this.featureBranchCount < this.featureData.length) {
          babyBranch = this.makeFeatureBranch(branch)
        } else {
          babyBranch = branch.makeBaby(this.branchRules, this.goal)
        }

        if (babyTrunk  && !shouldStop) newBranches.push(babyTrunk)
        if (babyBranch && !shouldStop) newBranches.push(babyBranch)
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

  /**
   * Create a feature branch from parent: applies color and registers it for hover hit-testing.
   * Isolates all feature-injection logic from the growth loop in step().
   */
  private makeFeatureBranch(parent: TreeBranch): TreeBranch | null {
    const baby = parent.makeBaby(this.branchRules, this.goal)
    if (!baby) return null
    const feat = this.featureData[this.featureBranchCount]
    baby.color = [...feat.color] as Color3
    this.featurePrimaryBranches.push({ branch: baby, title: feat.title, status: feat.status })
    this.featureBranchCount++
    return baby
  }

  // ─── Traversal ───────────────────────────────────────────────────────────────

  private collectSubtreeEntities(
    branch: TreeBranch,
    title: string,
    status: string,
    depth: number,
  ): void {
    if (depth > COLLECT_MAX_DEPTH) return
    const entity = this.entityMap.get(branch)
    if (entity) this.featureEntityMap.set(entity, { title, status })
    for (const baby of branch.babies) this.collectSubtreeEntities(baby, title, status, depth + 1)
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

  // ─── Rendering ───────────────────────────────────────────────────────────────

  private createEntity(branch: TreeBranch): void {
    const entity = new pc.Entity('B')
    entity.addComponent('render', { type: 'cylinder' })
    entity.render!.meshInstances[0].material = this.getMaterial(branch.color)
    // Thin cylinders contribute negligible shadow detail but add significant shadow-pass cost.
    // Disabling here matches LeafSystem's approach — biggest single performance saving.
    entity.render!.castShadows   = false
    entity.render!.receiveShadows = false
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

    const thickness = Math.max(branch.size / THICKNESS_DIVISOR, MIN_THICKNESS)
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
      mat.emissive  = this.useEmissive
        ? new pc.Color(r * 0.7, g * 0.7, b * 0.7)
        : new pc.Color(0, 0, 0)
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
