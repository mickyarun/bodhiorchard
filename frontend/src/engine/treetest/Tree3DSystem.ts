// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
import type { WindSystem } from './WindSystem'
import type { BakedBranchGroup, BakedFeaturePrimary } from './treeCache'
import { createInstancedEntity } from './instancing'

/** Data returned by bakeInstanced — everything needed to persist + reconstruct. */
export interface BakedTreeExport {
  branchGroups: BakedBranchGroup[]
  primaries:    BakedFeaturePrimary[]
}

const GROW_SPEED             = 200 * WORLD_SCALE
const DEFAULT_ROOT_COLOR: Color3 = [180, 180, 180]
const THICKNESS_DIVISOR   = 14
const MIN_THICKNESS        = 0.003  // world units — prevents hairline artifacts on tiny branches
const COLLECT_MAX_DEPTH   = 30
const DEFAULT_LEVELS      = 16

export class Tree3DSystem {
  private app: pc.AppBase
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

  // ─── Wind sway state ────────────────────────────────────────────────────────
  // Whole-tree sway: rotates treeRoot entity at its base, so all branches move together.
  private windSystem: WindSystem | null = null
  private windReady = false   // true after growth completes and buildWindEntries() is called
  private treeWorldX = 0      // world position — used as spatial phase offset for wind
  private treeWorldZ = 0

  // Static scratch for wind rotation — zero GC in per-frame wind path
  private static readonly _windQuat = new pc.Quat()
  private static readonly _windAxis = new pc.Vec3()

  // Static scratch for the one-shot bake pass — one Mat4/Vec3/Quat reused
  // across every branch avoids ~64K × 4 throwaway allocations on large trees
  // (one bake call is ~5 ms GC when allocating per branch, ~0 ms when reused).
  private static readonly _bakeMat4  = new pc.Mat4()
  private static readonly _bakePos   = new pc.Vec3()
  private static readonly _bakeScale = new pc.Vec3()
  private static readonly _bakeQuat  = new pc.Quat()
  private static readonly _bakeDir   = new Vec3(0, 0, 0)

  // Epsilons shared between orient/bake paths. Co-locate named constants so a
  // change to numerical tolerance affects both entity-path rendering and the
  // instancing bake in lockstep.
  private static readonly DEGENERATE_LENGTH_EPSILON = 1e-6
  private static readonly DEGENERATE_DOT_THRESHOLD  = 0.9999
  private static readonly THICKNESS_SCALE           = 2

  // ─── Instancing bake state ─────────────────────────────────────────────────
  // Populated by bakeInstanced(). The per-color vertex buffers own GPU memory
  // that outlives this.entityMap entries and must be destroyed explicitly.
  private bakedEntities: pc.Entity[] = []
  private bakedVertexBuffers: pc.VertexBuffer[] = []

  // Shared unit cylinder mesh reused across every baked tree, keyed by device
  // so that hot-reload / multi-app scenarios don't hand out a mesh bound to a
  // stale graphics device (which would crash at first draw because the device's
  // program library wouldn't be registered for it).
  private static _cylinderMeshByDevice = new WeakMap<pc.GraphicsDevice, pc.Mesh>()

  constructor(app: pc.AppBase, options?: { useEmissive?: boolean }) {
    this.app = app
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
    this.resetGrowthState(rootColor, worldX, worldZ)

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
    this.windReady = false
    this.treeRoot.setRotation(new pc.Quat())
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

  /** The root entity that holds all branch entities. Used to parent leaves under the same transform. */
  getRoot(): pc.Entity { return this.treeRoot }

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

  // ─── Wind ─────────────────────────────────────────────────────────────────────

  /** Connect a WindSystem. Call before or after startTree(). */
  setWindSystem(wind: WindSystem): void { this.windSystem = wind }

  /**
   * Enable whole-tree wind sway. Call once after isGrowing() returns false.
   * The tree sways as a single rigid body by rotating the treeRoot entity
   * at its base — all branches and sub-entities move together naturally.
   */
  buildWindEntries(): void {
    this.windReady = !!this.tree
  }

  /**
   * Apply wind sway to the whole tree. Call every frame after growth is done.
   * Rotates the treeRoot entity around the wind axis — the entire tree
   * tilts as one unit, just like a real tree bending at its base.
   */
  applyWind(): void {
    if (!this.windSystem || !this.windReady) return

    const windDir = this.windSystem.getDirection()
    // Sway axis: perpendicular to wind direction in XZ plane
    const axis = Tree3DSystem._windAxis.set(
      -Math.sin(windDir), 0, Math.cos(windDir),
    )

    // Use tree's actual world position for spatial phase — each tree sways differently
    const swayDeg = this.windSystem.getBranchSway(
      this.treeWorldX, this.treeWorldZ, 1.0, 0.0,
    )

    const windQuat = Tree3DSystem._windQuat
    windQuat.setFromAxisAngle(axis, swayDeg)
    this.treeRoot.setRotation(windQuat)
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
      // Scale trunk size with feature count so visual size reflects repo scope:
      //   N=0  → 25% (bare stub)   N=1  → ~40% (sapling)
      //   N=5  → ~65% (mid-size)   N=16 → 100% (standard)
      // Uses N^0.35 power curve — same exponent family as the large-N branch.
      const scaleFactor = N === 0 ? 0.25 : Math.min(Math.pow(N / DEFAULT_LEVELS, 0.35), 1.0)
      return defaultRoot * scaleFactor
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

  // ─── Hardware-instancing bake ────────────────────────────────────────────
  //
  // After growth completes the branch transforms are static. Keeping one
  // `pc.Entity` + cylinder render component per branch gives us 60k–64k draw
  // calls per fully-grown tree (see scaleRulesForFeatureCount doc). This
  // method collapses every finished branch into a single instanced draw call
  // per unique color by writing each branch's world matrix into a single
  // per-instance VertexBuffer and attaching it via `MeshInstance.setInstancing`.
  //
  // Primary feature branches (`featurePrimaryBranches`) survive as invisible
  // pick proxies — their render component is stripped but the entity stays in
  // the scene graph with its `pickable` tag, moved to the primary's midpoint
  // so TreePickerSystem's screen-space distance test hits the visible stem.
  //
  // Call once from the growth-complete handler, BEFORE buildFeatureEntityMap.
  //
  // Returns the packed matrices + primary midpoints so callers can persist them
  // to IndexedDB (treeCache). A fresh tree discards the return value; a tree
  // being saved to cache hands it to saveTreeCache().
  bakeInstanced(): BakedTreeExport {
    const branchGroups: BakedBranchGroup[] = []
    const primaries: BakedFeaturePrimary[] = []
    if (!this.tree) return { branchGroups, primaries }

    // Pass 1: count per color + stash the Color3 for each key. Lets us allocate
    // right-sized Float32Arrays per group without intermediate Mat4[] buffers,
    // which on N=250 trees previously meant ~64K Mat4 allocations per bake.
    const groupInfo = new Map<string, { color: Color3; count: number }>()
    this.countBranchesByColor(this.tree, groupInfo, 0)

    // Pass 2: allocate each group's final Float32Array up-front and a running
    // write-offset, then walk again writing world matrices directly via a
    // single static scratch Mat4 (see _bakeMat4). Zero per-branch allocation.
    const groupBuffers = new Map<string, { color: Color3; matrices: Float32Array; offset: number }>()
    for (const [key, info] of groupInfo) {
      groupBuffers.set(key, { color: info.color, matrices: new Float32Array(info.count * 16), offset: 0 })
    }
    this.writeBranchMatrices(this.tree, groupBuffers, 0)

    for (const [colorKey, buf] of groupBuffers) {
      const count = buf.matrices.length / 16
      if (count === 0) continue
      this.attachInstancedBranchEntity(colorKey, buf.matrices, count)
      branchGroups.push({ colorKey, color: buf.color, matrices: buf.matrices, count })
    }

    this.convertPrimariesToPickProxies(primaries)
    return { branchGroups, primaries }
  }

  /**
   * Reconstruct a fully-grown tree from a cached bake, skipping the growth
   * animation entirely. Called by ProceduralTreeSystem when loadTreeCache()
   * returns a hit. Must mirror the end state of startTree() + update()-to-done
   * + bakeInstanced(): per-color instanced MeshInstances, primary pick-proxy
   * entities at midpoints, no live growth, ready for wind + picking.
   */
  loadFromCache(
    exported: BakedTreeExport,
    rootColor: Color3,
    worldX: number,
    worldZ: number,
  ): void {
    this.resetGrowthState(rootColor, worldX, worldZ)
    // Cache hit means the tree is already fully grown — enable wind immediately
    // instead of waiting for buildWindEntries() after a growth-complete event.
    this.windReady = true

    // Recreate per-color instanced mesh instances + their materials.
    for (const group of exported.branchGroups) {
      // Re-seed the material cache so later getMaterial() lookups hit (e.g. if
      // a later re-grow ever goes through the per-entity path again).
      if (!this.matCache.has(group.colorKey)) {
        this.getMaterial(group.color)
      }
      this.attachInstancedBranchEntity(group.colorKey, group.matrices, group.count)
    }

    // Recreate primary-feature pick proxies. Render-less entities — picked by
    // position + tag, not rendered.
    for (const p of exported.primaries) {
      const entity = new pc.Entity('PrimaryProxy')
      entity.setPosition(p.midpoint[0], p.midpoint[1], p.midpoint[2])
      this.treeRoot.addChild(entity)
      this.featureEntityMap.set(entity, { title: p.title, status: p.status })
    }
  }

  // Shared full reset used by startTree() (before growth) and loadFromCache()
  // (before restoring a baked tree). Both paths must start from a clean slate
  // for idempotence when the same Tree3DSystem is reused across runs.
  private resetGrowthState(rootColor: Color3, worldX: number, worldZ: number): void {
    this.clearEntities()
    this.destroyMaterials()
    this.activeBranches = []
    this.tree = null
    this.trunkChain.clear()
    this.featurePrimaryBranches = []
    this.featureEntityMap.clear()
    this.featureBranchCount = 0
    this.growing = false
    this.windReady = false

    this.rootColor  = rootColor
    this.treeWorldX = worldX
    this.treeWorldZ = worldZ
    this.treeRoot.setRotation(new pc.Quat())

    // Rules must be re-defaulted so a subsequent startTree() doesn't inherit
    // scaled-for-large-N trunk minSize from a prior run.
    this.trunkRules    = defaultTrunk()
    this.branchRules   = defaultBranch()
    this.offTrunkRules = defaultTrunk()
    this.growSpeed     = GROW_SPEED
  }

  private attachInstancedBranchEntity(colorKey: string, matrices: Float32Array, count: number): void {
    const material = this.matCache.get(colorKey)
    if (!material || count === 0) return
    const { entity, vb } = createInstancedEntity(
      this.app.graphicsDevice,
      this.getCylinderMesh(),
      material,
      matrices,
      count,
      `BakedBranches_${colorKey}`,
    )
    this.treeRoot.addChild(entity)
    this.bakedEntities.push(entity)
    this.bakedVertexBuffers.push(vb)
  }

  // Converts each surviving primary-feature branch entity into a render-less
  // pick proxy at the branch midpoint, then destroys all other branch entities.
  // Appends the same primaries (with midpoints) to `out` for cache export.
  private convertPrimariesToPickProxies(out: BakedFeaturePrimary[]): void {
    const primaryMeta = new Map(this.featurePrimaryBranches.map(fp => [fp.branch, { title: fp.title, status: fp.status }]))
    // Collect keys first — we mutate the Map during iteration.
    for (const branch of Array.from(this.entityMap.keys())) {
      const entity = this.entityMap.get(branch)
      if (!entity) continue
      const meta = primaryMeta.get(branch)
      if (meta) {
        entity.removeComponent('render')
        // Move to midpoint so the screen-space picker (FEATURE_HOVER_PX=18)
        // hits somewhere on the visible branch stem, not at its hidden base.
        const root = branch.root
        const tip = branch.getTip()
        const mx = (root.x + tip.x) * 0.5
        const my = (root.y + tip.y) * 0.5
        const mz = (root.z + tip.z) * 0.5
        entity.setPosition(mx, my, mz)
        out.push({ title: meta.title, status: meta.status, midpoint: [mx, my, mz] })
      } else {
        entity.destroy()
        this.entityMap.delete(branch)
      }
    }
  }

  private countBranchesByColor(
    branch: TreeBranch,
    out: Map<string, { color: Color3; count: number }>,
    depth: number,
  ): void {
    if (depth > COLLECT_MAX_DEPTH) return
    if (branch.growthSize > 0) {
      const key = `${branch.color[0]}_${branch.color[1]}_${branch.color[2]}`
      const entry = out.get(key)
      if (entry) {
        entry.count++
      } else {
        out.set(key, { color: [...branch.color] as Color3, count: 1 })
      }
    }
    for (const baby of branch.babies) this.countBranchesByColor(baby, out, depth + 1)
  }

  private writeBranchMatrices(
    branch: TreeBranch,
    buffers: Map<string, { color: Color3; matrices: Float32Array; offset: number }>,
    depth: number,
  ): void {
    if (depth > COLLECT_MAX_DEPTH) return
    if (branch.growthSize > 0) {
      const key = `${branch.color[0]}_${branch.color[1]}_${branch.color[2]}`
      const buf = buffers.get(key)
      if (buf) {
        this.writeBranchMatrixAt(branch, buf.matrices, buf.offset)
        buf.offset += 16
      }
    }
    for (const baby of branch.babies) this.writeBranchMatrices(baby, buffers, depth + 1)
  }

  // Write a single branch's world matrix into the flat buffer at byte offset.
  // Uses static scratch Mat4/Vec3/Quat — zero allocation across the entire bake.
  private writeBranchMatrixAt(branch: TreeBranch, out: Float32Array, offset: number): void {
    const dir = Tree3DSystem._bakeDir
    branch.getGrowTipInto(dir)
    const dirLen = dir.length()
    const thickness = Math.max(branch.size / THICKNESS_DIVISOR, MIN_THICKNESS)

    Tree3DSystem._bakePos.set(
      branch.root.x + dir.x * 0.5,
      branch.root.y + dir.y * 0.5,
      branch.root.z + dir.z * 0.5,
    )
    Tree3DSystem._bakeScale.set(thickness * Tree3DSystem.THICKNESS_SCALE, dirLen, thickness * Tree3DSystem.THICKNESS_SCALE)
    this.writeRotationAlignToY(dir, dirLen, Tree3DSystem._bakeQuat)
    Tree3DSystem._bakeMat4.setTRS(Tree3DSystem._bakePos, Tree3DSystem._bakeQuat, Tree3DSystem._bakeScale)

    out.set(Tree3DSystem._bakeMat4.data, offset)
  }

  // Populates `outQuat` with a rotation that aligns +Y to `dir`. Mirrors the
  // logic in orientAlongDirection() but writes into a caller-owned Quat so the
  // bake pass stays allocation-free.
  private writeRotationAlignToY(dir: Vec3, len: number, outQuat: pc.Quat): void {
    outQuat.set(0, 0, 0, 1)
    if (len < Tree3DSystem.DEGENERATE_LENGTH_EPSILON) return
    const ny = dir.y / len
    if (ny > Tree3DSystem.DEGENERATE_DOT_THRESHOLD) return
    if (ny < -Tree3DSystem.DEGENERATE_DOT_THRESHOLD) {
      outQuat.setFromEulerAngles(180, 0, 0)
      return
    }
    // Axis = up × target; w = 1 + dot. Normalize in-place.
    const cx = dir.z / len
    const cz = -dir.x / len
    outQuat.set(cx, 0, cz, 1 + ny)
    const mag = Math.sqrt(outQuat.x * outQuat.x + outQuat.y * outQuat.y + outQuat.z * outQuat.z + outQuat.w * outQuat.w)
    outQuat.x /= mag; outQuat.y /= mag; outQuat.z /= mag; outQuat.w /= mag
  }

  private getCylinderMesh(): pc.Mesh {
    const device = this.app.graphicsDevice
    const cached = Tree3DSystem._cylinderMeshByDevice.get(device)
    if (cached) return cached
    // Build the unit cylinder directly against this app's graphics device.
    // pc.CylinderGeometry defaults: radius 0.5, height 1, 5 height segments,
    // 20 cap segments, centered at origin with Y axis vertical — matches the
    // primitive 'cylinder' in dimensions and is what TreeBranch transforms
    // expect (scale.y = branch length, thickness → scale.xz).
    const mesh = pc.Mesh.fromGeometry(device, new pc.CylinderGeometry())
    Tree3DSystem._cylinderMeshByDevice.set(device, mesh)
    return mesh
  }

  private clearEntities(): void {
    for (const entity of this.entityMap.values()) entity.destroy()
    this.entityMap.clear()
    this.clearBaked()
  }

  private clearBaked(): void {
    for (const e of this.bakedEntities) e.destroy()
    for (const vb of this.bakedVertexBuffers) vb.destroy()
    this.bakedEntities = []
    this.bakedVertexBuffers = []
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
