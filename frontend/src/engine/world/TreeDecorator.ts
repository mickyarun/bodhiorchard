/**
 * TreeDecorator — Attach flowers (features), buds, and mushrooms (threats) around trees.
 *
 * Flowers and buds are placed on the GROUND around the tree base in a ring scatter,
 * not inside the canopy. Since trees are scaled 8–15×, all local positions and scales
 * are compensated by the inverse of the tree's uniform scale to achieve correct
 * world-space placement.
 *
 * Threats (mushrooms) remain at the tree base in a tight cluster.
 */
import * as pc from 'playcanvas'
import type { EngineFeature, EngineBUD, EngineThreat } from '../types'
import { AssetLoader } from '../assets/AssetLoader'
import { getFeatureFlowerGLB, getBudFlowerGLB, getThreatGLB } from '../assets/AssetManifest'
import { randRange } from '../utils/MathUtils'

/** World-space radius range for flower ring around tree base. */
const FLOWER_RING_MIN = 1.5
const FLOWER_RING_MAX = 3.0

/** World-space scale range for decoration flowers. */
const FLOWER_SCALE_MIN = 3.0
const FLOWER_SCALE_MAX = 5.0

/** World-space radius for threat mushrooms (tight to trunk). */
const THREAT_RADIUS = 1.0

/** Cap on decorations per type to prevent clutter. */
const MAX_FEATURES = 5
const MAX_BUDS = 3
const MAX_THREATS = 3

export class TreeDecorator {
  private loader: AssetLoader

  constructor(loader: AssetLoader) {
    this.loader = loader
  }

  /** Attach feature flowers on the ground around a tree's base. */
  async decorateFeatures(tree: pc.Entity, features: EngineFeature[]): Promise<void> {
    const inv = 1 / tree.getLocalScale().x // inverse of uniform tree scale
    const capped = features.slice(0, MAX_FEATURES)

    for (let i = 0; i < capped.length; i++) {
      const feature = capped[i]
      const glb = getFeatureFlowerGLB(i)
      const asset = await this.loader.load(glb)
      const flower = this.loader.instance(asset)

      // Ring scatter on ground — evenly spaced with jitter
      const angle = (i / capped.length) * Math.PI * 2 + randRange(-0.3, 0.3)
      const worldRadius = randRange(FLOWER_RING_MIN, FLOWER_RING_MAX)
      const wx = Math.cos(angle) * worldRadius
      const wz = Math.sin(angle) * worldRadius

      // Compensate for parent tree scale: local = world / treeScale
      flower.setLocalPosition(wx * inv, 0, wz * inv)
      const s = randRange(FLOWER_SCALE_MIN, FLOWER_SCALE_MAX) * inv
      flower.setLocalScale(s, s, s)

      flower.name = `Feature_${feature.title}`
      flower.tags.add('pickable')

      ;(flower as unknown as Record<string, unknown>)._userData = {
        type: 'feature',
        title: feature.title,
        status: feature.status,
        repoName: feature.repo_name,
      }

      tree.addChild(flower)
    }
  }

  /** Attach BUD flower buds on the ground around a tree's base. */
  async decorateBuds(tree: pc.Entity, buds: EngineBUD[]): Promise<void> {
    const inv = 1 / tree.getLocalScale().x
    const capped = buds.slice(0, MAX_BUDS)

    for (let i = 0; i < capped.length; i++) {
      const bud = capped[i]
      const glb = getBudFlowerGLB(bud.status)
      const asset = await this.loader.load(glb)
      const budEntity = this.loader.instance(asset)

      // Ring scatter — offset from features to avoid overlap
      const angle = (i / capped.length) * Math.PI * 2 + Math.PI / 3 + randRange(-0.2, 0.2)
      const worldRadius = randRange(FLOWER_RING_MIN, FLOWER_RING_MAX)
      const wx = Math.cos(angle) * worldRadius
      const wz = Math.sin(angle) * worldRadius

      budEntity.setLocalPosition(wx * inv, 0, wz * inv)
      const s = randRange(2.5, 4.0) * inv
      budEntity.setLocalScale(s, s, s)

      budEntity.name = `BUD_${bud.bud_number}`
      budEntity.tags.add('pickable')

      ;(budEntity as unknown as Record<string, unknown>)._userData = {
        type: 'bud',
        budNumber: bud.bud_number,
        title: bud.title,
        status: bud.status,
        repoName: bud.repo_name,
      }

      tree.addChild(budEntity)
    }
  }

  /** Attach threat mushrooms at a tree's base. */
  async decorateThreats(tree: pc.Entity, threats: EngineThreat[]): Promise<void> {
    const inv = 1 / tree.getLocalScale().x
    const capped = threats.slice(0, MAX_THREATS)

    for (let i = 0; i < capped.length; i++) {
      const threat = capped[i]
      const glb = getThreatGLB(threat.severity)
      const asset = await this.loader.load(glb)
      const mushroom = this.loader.instance(asset)

      // Tight cluster at tree base
      const angle = (i / capped.length) * Math.PI * 2 + randRange(-0.2, 0.2)
      const worldRadius = randRange(0.5, THREAT_RADIUS)
      const wx = Math.cos(angle) * worldRadius
      const wz = Math.sin(angle) * worldRadius

      mushroom.setLocalPosition(wx * inv, 0, wz * inv)
      const s = (threat.severity === 'critical' ? 3.0 : randRange(1.5, 2.5)) * inv
      mushroom.setLocalScale(s, s, s)

      mushroom.name = `Threat_${threat.id}`
      mushroom.tags.add('pickable')

      ;(mushroom as unknown as Record<string, unknown>)._userData = {
        type: 'threat',
        id: threat.id,
        title: threat.title,
        severity: threat.severity,
        module: threat.module,
      }

      tree.addChild(mushroom)
    }
  }
}
