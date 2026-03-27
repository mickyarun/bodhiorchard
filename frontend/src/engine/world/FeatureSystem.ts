/**
 * FeatureSystem — Hangs status-colored fruit spheres on repo entities.
 *
 * For tree repos: places fruits at the outer edges of the canopy.
 * For graph spheres: uses offsets from RepoVisualization.getFeatureOffsets().
 *
 * Replaces TreeDecorator.decorateFeatures() (ground-level flowers).
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { EngineFeature } from '../types'
import { setTreeData, type TreeFeatureNodeData } from './TreeNodeData'
import { hashString } from '../utils/MathUtils'

// ─── Constants ───────────────────────────────────

const MAX_FEATURES = 5

/**
 * Canopy placement zone (model-space). Fruits are placed at the outer
 * edge of the canopy volume. Native Kenney trees are ~0.7 wide (radius ~0.35).
 */
const CANOPY_RING_RADIUS = 0.22
const CANOPY_Y_MIN = 0.6  // fraction of model height (canopy start)
const CANOPY_Y_MAX = 0.85 // fraction of model height (canopy top)

/** Fruit hang below canopy placement point (model-space). */
const FRUIT_DROP = 0.03

// Status → fruit visual properties
const STATUS_CONFIG: Record<string, {
  radius: number
  matKey: string
  color: [number, number, number]
  emissive?: [number, number, number]
}> = {
  planned:     { radius: 0.025, matKey: 'fruit_planned', color: [0.4, 0.7, 0.3] },
  in_progress: { radius: 0.03,  matKey: 'fruit_inprog',  color: [0.95, 0.6, 0.15], emissive: [0.3, 0.15, 0] },
  implemented: { radius: 0.04,  matKey: 'fruit_done',    color: [0.9, 0.2, 0.2],   emissive: [0.4, 0.1, 0.05] },
}

const DEFAULT_STATUS = STATUS_CONFIG['planned']

// ─── System ──────────────────────────────────────

export class FeatureSystem {
  private matKeysUsed: string[] = []
  private fruitEntities = new Map<string, pc.Entity>()
  private allPickables: pc.Entity[] = []
  private fruitList: { entity: pc.Entity; seed: number; baseY: number }[] = []
  private elapsed = 0

  /**
   * Build fruit spheres for all repo entities.
   * Call after RepoVisualization.build() so treeMap is populated.
   *
   * @param featureOffsets Optional callback for custom placement (e.g. graph sphere Fibonacci).
   *   If omitted, uses default canopy placement (tree-specific).
   */
  build(
    _app: Application,
    materials: MaterialFactory,
    features: EngineFeature[],
    treeMap: Map<string, pc.Entity>,
    featureOffsets?: (repoName: string, count: number) => Array<{ x: number; y: number; z: number }>,
  ): void {
    this.elapsed = 0

    // Pre-index features by repo
    const featuresByRepo = new Map<string, EngineFeature[]>()
    for (const f of features) {
      if (!f.repo_name) continue
      const arr = featuresByRepo.get(f.repo_name)
      if (arr) arr.push(f)
      else featuresByRepo.set(f.repo_name, [f])
    }

    // Create shared fruit materials (one per status)
    const fruitMats = new Map<string, pc.StandardMaterial>()
    for (const cfg of Object.values(STATUS_CONFIG)) {
      if (!fruitMats.has(cfg.matKey)) {
        this.matKeysUsed.push(cfg.matKey)
        fruitMats.set(cfg.matKey, materials.getColor(
          cfg.matKey, cfg.color[0], cfg.color[1], cfg.color[2],
          { metalness: 0.15, gloss: 0.7, emissive: cfg.emissive },
        ))
      }
    }

    // Place fruits per repo entity
    for (const [repoName, treeEntity] of treeMap) {
      const repoFeatures = featuresByRepo.get(repoName)
      if (!repoFeatures || repoFeatures.length === 0) continue

      const capped = repoFeatures.slice(0, MAX_FEATURES)

      // Get offsets: custom (graph spheres) or default canopy placement (trees)
      const customOffsets = featureOffsets?.(repoName, capped.length)

      const modelHeight = customOffsets ? 0 : getModelHeight(treeEntity)
      const inv = 1 / treeEntity.getLocalScale().x

      for (let j = 0; j < capped.length; j++) {
        const feature = capped[j]
        const n = capped.length
        const seed = hashString(feature.title)

        let fruitX: number, fruitY: number, fruitZ: number
        if (customOffsets && customOffsets[j]) {
          // Custom placement (e.g. Fibonacci sphere around graph node)
          fruitX = customOffsets[j].x
          fruitY = customOffsets[j].y
          fruitZ = customOffsets[j].z
        } else {
          // Default canopy placement for trees
          const angle = (j / n) * Math.PI * 2 + (seed % 100) * 0.006
          const heightFrac = CANOPY_Y_MIN + ((j + seed % 5) / (n + 4)) * (CANOPY_Y_MAX - CANOPY_Y_MIN)
          fruitX = CANOPY_RING_RADIUS * Math.cos(angle)
          fruitY = modelHeight * heightFrac - FRUIT_DROP
          fruitZ = CANOPY_RING_RADIUS * Math.sin(angle)
        }

        // Build pickable data
        const nodeData: TreeFeatureNodeData = {
          type: 'tree_feature',
          title: feature.title,
          status: feature.status,
          repoName: feature.repo_name,
          linkedRepos: feature.linked_repos,
          codeLocations: feature.code_locations,
          branchName: feature.branch_name,
          fromBud: feature.from_bud,
          sourceRef: feature.source_ref,
        }

        // Fruit sphere (local-space, child of repo entity)
        const cfg = STATUS_CONFIG[feature.status] ?? DEFAULT_STATUS
        const fruitMat = fruitMats.get(cfg.matKey)

        const fruit = new pc.Entity(`Fruit_${feature.title.slice(0, 20)}`)
        fruit.addComponent('render', { type: 'sphere' })
        const fr = customOffsets ? cfg.radius * 6 : cfg.radius * 2 * inv
        fruit.setLocalScale(fr, fr, fr)
        fruit.setLocalPosition(fruitX, fruitY, fruitZ)

        if (fruitMat) fruit.render!.meshInstances[0].material = fruitMat

        fruit.tags.add('pickable')
        setTreeData(fruit, nodeData)
        treeEntity.addChild(fruit)

        this.fruitEntities.set(feature.title, fruit)
        this.allPickables.push(fruit)
        this.fruitList.push({ entity: fruit, seed, baseY: fruitY })
      }
    }
  }

  /** Get fruit entity by feature title (for FeatureLinkArcs endpoint). */
  getFruitEntity(featureTitle: string): pc.Entity | undefined {
    return this.fruitEntities.get(featureTitle)
  }

  /** Get all pickable entities (fruits) for TreePickerSystem. */
  getAllPickableEntities(): pc.Entity[] {
    return this.allPickables
  }

  /** Per-frame update — gentle Y-axis bob on fruit spheres (absolute, no drift). */
  update(dt: number): void {
    this.elapsed += dt
    for (const { entity, seed, baseY } of this.fruitList) {
      const pos = entity.getLocalPosition()
      const bob = Math.sin(this.elapsed * 1.5 + seed * 0.7) * 0.005
      entity.setLocalPosition(pos.x, baseY + bob, pos.z)
    }
  }

  /** Release materials and clear references. Entities destroyed via parent tree. */
  destroy(materials: MaterialFactory): void {
    for (const key of this.matKeysUsed) {
      materials.release(key)
    }
    this.matKeysUsed = []
    this.fruitEntities.clear()
    this.allPickables = []
    this.fruitList = []
    this.elapsed = 0
  }
}

/** Get the model-space height of an entity by scanning its mesh AABBs. */
function getModelHeight(entity: pc.Entity): number {
  const renders = entity.findComponents('render') as pc.RenderComponent[]
  let maxY = 0
  for (const rc of renders) {
    for (const mi of rc.meshInstances) {
      const top = mi.mesh.aabb.getMax().y
      if (top > maxY) maxY = top
    }
  }
  return maxY
}
