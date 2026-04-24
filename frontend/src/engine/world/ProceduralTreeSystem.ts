// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * ProceduralTreeSystem — RepoVisualization using procedural Tree3DSystem growth.
 *
 * Replaces the static Kenney GLB trees. Each repo becomes an animated procedural tree:
 *   - Trunk color mapped from repo health (thriving→green … wilted→reddish)
 *   - Feature branches colored by status (planned/in_progress/implemented)
 *   - Grows frame-by-frame via update(dt) — trees animate during scene load
 *   - Billboard label appears once growth completes (above canopy tip)
 *   - Uses proper PBR diffuse colors (no emissive glow — garden engine is daylit)
 *
 * Buds/threats decoration and relationship arcs are wired in a later phase.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { EngineData, EngineFeature, EngineRepoData } from '../types'
import type { WorldLayout } from './WorldLayout'
import type { RepoVisualization } from './RepoVisualization'
import type { ExclusionZone } from '../utils/MathUtils'
import { Tree3DSystem } from '../treetest/Tree3DSystem'
import { LeafSystem } from '../treetest/LeafSystem'
import type { Color3 } from '../treetest/TreeRules'
import { WORLD_SCALE } from '../treetest/TreeRules'
import { LabelRenderer } from '../rendering/LabelRenderer'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { setTreeData, type TreeFeatureNodeData } from './TreeNodeData'
import {
  loadTreeCache,
  saveTreeCache,
  pruneLRU,
  computeCacheKey,
  type BakedLeafGroup,
  type BakedTree,
} from '../treetest/treeCache'

// ─── Constants ───────────────────────────────────────────────────────────────

/**
 * Distinct trunk base colors — one per repo, cycled by index.
 * Chosen to be visually differentiated in a daylit PBR scene (no emissive).
 */
const TRUNK_PALETTE: Color3[] = [
  [ 70, 160, 230],  // sky blue
  [220, 120,  40],  // amber
  [160,  80, 200],  // violet
  [ 50, 190, 140],  // teal
  [220,  60,  80],  // coral
  [180, 200,  50],  // lime
  [ 80, 120, 220],  // indigo
  [230, 160,  50],  // gold
  [100, 200,  80],  // grass green
  [200,  80, 150],  // pink
  [ 60, 180, 200],  // cyan
  [200, 130,  70],  // tan
]

/** Pick trunk color by repo index — cycles through the palette. */
function trunkColor(index: number): Color3 {
  return TRUNK_PALETTE[index % TRUNK_PALETTE.length]
}

/** Max features injected as colored branches per tree. */
const MAX_FEATURES = 250

/** Gap above the highest terminal tip for the repo label (world units). */
const LABEL_GAP = 0.3

/** Default label height if tree has no tips (shouldn't happen in practice). */
const DEFAULT_LABEL_Y = 4.0

// ─── Types ───────────────────────────────────────────────────────────────────

interface ProceduralEntry {
  tree:            Tree3DSystem
  leaves:          LeafSystem          // one per repo — spawnLeaves() called on growth complete
  container:       pc.Entity           // at (worldX, 0, worldZ) — picked entity, position anchor
  repoName:        string
  repo:            EngineRepoData
  worldX:          number
  worldZ:          number
  label:           pc.Entity | null    // null until growth completes / cache loads
  done:            boolean
  featuresByTitle: Map<string, EngineFeature>  // title → full feature data (for picking)
  cacheKey:        string              // stable key for treeCache; "__unimplemented__*" disables caching
  rootColor:       Color3              // palette-cycled trunk color — needed for cache save
}

// ─── System ──────────────────────────────────────────────────────────────────

export class ProceduralTreeSystem implements RepoVisualization {
  private readonly materials: MaterialFactory
  private appRef: Application | null = null
  private root:   pc.Entity | null   = null
  private entries: ProceduralEntry[] = []
  private treeMap = new Map<string, pc.Entity>()
  // All 'pickable' entities: containers (registered at build) + feature branches (registered on growth complete)
  private allPickableEntities: pc.Entity[] = []

  constructor(materials: MaterialFactory) {
    this.materials = materials
  }

  async build(
    app: Application,
    data: EngineData,
    layout: WorldLayout,
  ): Promise<ExclusionZone[]> {
    this.appRef = app
    this.root   = new pc.Entity('ProceduralTreeSystem')
    this.entries = []
    this.treeMap.clear()
    this.allPickableEntities = []

    const positions     = layout.getTreePositions(data.repos.length)
    const exclusionZones: ExclusionZone[] = []

    // Pre-index features by repo_name for O(1) lookup
    const featuresByRepo = new Map<string, EngineFeature[]>()
    for (const f of data.features) {
      if (!f.repo_name) continue
      const arr = featuresByRepo.get(f.repo_name)
      if (arr) arr.push(f); else featuresByRepo.set(f.repo_name, [f])
    }

    // Precompute cache keys per repo, then fire the IndexedDB lookups in
    // parallel. Sequential awaits would multiply by 21 (~1 RTT each even from
    // IDB) and stall the boot path.
    const perRepoFeatures: EngineFeature[][] = []
    const cacheKeys: string[] = []
    for (let i = 0; i < data.repos.length; i++) {
      const repo = data.repos[i]
      const repoFeatures = (featuresByRepo.get(repo.repo_name) ?? []).slice(0, MAX_FEATURES)
      perRepoFeatures.push(repoFeatures)
      cacheKeys.push(computeCacheKey({
        repoName:        repo.repo_name,
        trunkColorIndex: i % TRUNK_PALETTE.length,
        features:        repoFeatures.map(f => ({ title: f.title, status: f.status })),
      }))
    }
    const cacheHits = await Promise.all(cacheKeys.map(k => loadTreeCache(k)))

    for (let i = 0; i < data.repos.length; i++) {
      const repo = data.repos[i]
      const pos  = positions[i]

      // Container entity at (x, 0, z) — acts as the "tree entity" for picking + position queries
      const container = new pc.Entity(`Tree_${repo.repo_name}`)
      container.setPosition(pos.x, 0, pos.z)
      container.tags.add('pickable')
      setTreeData(container, {
        type:         'tree_repo',
        repoName:     repo.repo_name,
        health:       repo.health,
        growthStage:  repo.growth_stage,
        branchCount:  repo.branches.length,
        totalFiles:   repo.total_files,
        totalCommits: repo.total_commits,
      })
      this.root.addChild(container)
      this.treeMap.set(repo.repo_name, container)

      // Map EngineFeature → Tree3DSystem feature format
      const repoFeatures = perRepoFeatures[i]
      const color = trunkColor(i)
      const treeFeatures = repoFeatures.map(f => ({
        color:  color,
        title:  f.title,
        status: f.status,
      }))

      // Index features by title for fast lookup when tagging branch entities after growth
      const featuresByTitle = new Map<string, EngineFeature>()
      for (const f of repoFeatures) featuresByTitle.set(f.title, f)

      // Procedural tree — no emissive glow (garden engine uses PBR daylit scene)
      const tree   = new Tree3DSystem(app.app, { useEmissive: false })
      const leaves = new LeafSystem(app.app, this.materials)
      tree.setFeatures(treeFeatures)

      const entry: ProceduralEntry = {
        tree, leaves, container, repoName: repo.repo_name, repo,
        worldX: pos.x, worldZ: pos.z,
        label: null, done: false, featuresByTitle,
        cacheKey: cacheKeys[i], rootColor: color,
      }
      this.entries.push(entry)

      // Container is immediately pickable (repo click/hover)
      this.allPickableEntities.push(container)

      exclusionZones.push({
        x: pos.x, z: pos.z,
        radius: estimatedRadius(repoFeatures.length),
      })

      const cached = cacheHits[i]
      if (cached) {
        // Cache hit: skip growth, restore instanced state directly.
        tree.loadFromCache(
          { branchGroups: cached.branchGroups, primaries: cached.primaries },
          color, pos.x, pos.z,
        )
        if (cached.leafGroup) leaves.loadFromCache(cached.leafGroup)
        this.handleTreeReady(entry, cached.labelY)
        entry.done = true
      } else {
        tree.startTree(color, pos.x, 0, pos.z)
      }
    }

    app.root.addChild(this.root)
    // Opportunistic background eviction — never awaited, never blocks boot.
    pruneLRU().catch(() => {})
    return exclusionZones
  }

  /**
   * Shared side effects that fire once a tree reaches its fully-grown baked
   * state, whether from a live growth run or a restored cache load:
   *   - tag primary-feature pick proxies with TreeNodeData
   *   - add them to allPickableEntities
   *   - create + place the billboard label
   *
   * The tree's featureEntityMap must already be populated before this call.
   */
  private handleTreeReady(entry: ProceduralEntry, labelY: number): void {
    if (!this.appRef) return
    for (const [entity, { title, status }] of entry.tree.getFeatureEntityMap()) {
      const feat = entry.featuresByTitle.get(title)
      const nodeData: TreeFeatureNodeData = {
        type:          'tree_feature',
        title,
        status,
        repoName:      entry.repoName,
        linkedRepos:   feat?.linked_repos   ?? [],
        codeLocations: feat?.code_locations ?? null,
        branchName:    feat?.branch_name    ?? null,
        fromBud:       feat?.from_bud       ?? null,
        sourceRef:     feat?.source_ref     ?? null,
      }
      entity.tags.add('pickable')
      setTreeData(entity, nodeData)
      this.allPickableEntities.push(entity)
    }
    const label = LabelRenderer.create(this.appRef, entry.repoName)
    label.setLocalPosition(0, labelY, 0)
    entry.container.addChild(label)
    entry.label = label
  }

  /** Advance all growing trees. Spawn leaves + labels on completion. Animate leaves each frame. */
  update(dt: number): void {
    if (!this.appRef) return

    for (const entry of this.entries) {
      if (!entry.done) {
        const stillGrowing = entry.tree.update(dt)
        if (!stillGrowing) {
          entry.done = true

          // Collapse 60k+ per-branch entities into a handful of hardware-instanced
          // draw calls (one per color). Descendants destroyed; primary feature
          // branches stay as invisible pick proxies. Must run BEFORE
          // buildFeatureEntityMap so the map only walks surviving primaries.
          const treeExport = entry.tree.bakeInstanced()
          entry.tree.buildFeatureEntityMap()

          // Compute canopy-top label Y from terminal tips BEFORE leaf spawn
          // destroys nothing relevant, but we keep the order stable.
          const tips = entry.tree.getTerminalTips()
          const labelY = tips.length > 0
            ? Math.max(...tips.map(t => t.position.y)) + LABEL_GAP
            : DEFAULT_LABEL_Y

          // Leaves spawn only if the repo has at least one implemented feature.
          // in_progress / planned repos show bare trees — leaves signal completion.
          const hasImplemented = [...entry.featuresByTitle.values()].some(f => f.status === 'implemented')
          let leafExport: BakedLeafGroup | null = null
          if (hasImplemented) {
            entry.leaves.spawnLeaves(tips, entry.tree.getRootColor())
            leafExport = entry.leaves.bakeInstanced()
          }

          this.handleTreeReady(entry, labelY)

          // Persist the baked tree so the next session can skip growth.
          // Structured-clone preserves the Float32Arrays; fire-and-forget.
          const payload: BakedTree = {
            schemaVersion: 1,
            cacheKey:      entry.cacheKey,
            savedAt:       Date.now(),
            branchGroups:  treeExport.branchGroups,
            leafGroup:     leafExport,
            primaries:     treeExport.primaries,
            labelY,
          }
          saveTreeCache(payload).catch(() => {})
        }
      }

      // Animate leaf wind sway every frame (no-op once leaves are baked)
      entry.leaves.update(dt)
    }
  }

  getTreePosition(repoName: string): pc.Vec3 | null {
    const entity = this.treeMap.get(repoName)
    return entity ? entity.getPosition().clone() : null
  }

  getTreeEntity(repoName: string): pc.Entity | undefined {
    return this.treeMap.get(repoName)
  }

  getTreeMap(): Map<string, pc.Entity> {
    return this.treeMap
  }

  /** All pickable entities: repo containers (available immediately) + feature branches (registered on growth complete). */
  getPickableEntities(): pc.Entity[] {
    return this.allPickableEntities
  }

  destroy(): void {
    // Release billboard GPU resources before entity.destroy() cascades
    for (const entry of this.entries) {
      if (entry.label && this.appRef) LabelRenderer.cleanup(this.appRef, entry.label)
      entry.leaves.destroy()
      entry.tree.destroy()
    }

    if (this.root) {
      this.root.destroy()
      this.root = null
    }
    this.entries = []
    this.treeMap.clear()
    this.allPickableEntities = []
    this.appRef = null
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Estimate exclusion zone radius from feature count.
 * Mirrors the rootSize formula in Tree3DSystem.scaleRulesForFeatureCount():
 *   defaultRoot = (120 / 0.75) × WORLD_SCALE ≈ 2.4
 *   for N > 16: rootSize scales as N^0.25
 * Exclusion zone = rootSize × 2, clamped to [4, 10] world units.
 */
function estimatedRadius(N: number): number {
  const defaultRoot = (120 / 0.75) * WORLD_SCALE
  const r = N <= 16 ? defaultRoot : defaultRoot * Math.pow(N / 16, 0.25)
  return Math.min(Math.max(r * 2, 4.0), 10.0)
}
