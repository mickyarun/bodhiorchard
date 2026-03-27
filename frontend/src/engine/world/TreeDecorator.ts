/**
 * TreeDecorator — Attach buds and mushrooms (threats) around tree bases.
 *
 * Features are handled by FeatureSystem (fruits in canopy).
 * BUDs and threats are placed on the GROUND around the tree base in a ring scatter.
 * Since trees are scaled 5–9×, all local positions and scales are compensated
 * by the inverse of the tree's uniform scale.
 */
import * as pc from 'playcanvas'
import type { EngineBUD, EngineThreat } from '../types'
import { AssetLoader } from '../assets/AssetLoader'
import { getBudFlowerGLB, getThreatGLB } from '../assets/AssetManifest'
import { randRange } from '../utils/MathUtils'
import { setTreeData } from './TreeNodeData'

/** World-space radius range for decoration ring around tree base. */
const FLOWER_RING_MIN = 1.5
const FLOWER_RING_MAX = 3.0

/** World-space radius for threat mushrooms (tight to trunk). */
const THREAT_RADIUS = 1.0

/** Cap on decorations per type to prevent clutter. */
const MAX_BUDS = 3
const MAX_THREATS = 3

export class TreeDecorator {
  private loader: AssetLoader

  constructor(loader: AssetLoader) {
    this.loader = loader
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

      setTreeData(budEntity, {
        type: 'tree_bud',
        budNumber: bud.bud_number,
        title: bud.title,
        status: bud.status,
        repoName: bud.repo_name,
      })

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

      setTreeData(mushroom, {
        type: 'tree_threat',
        id: threat.id,
        title: threat.title,
        severity: threat.severity,
        module: threat.module,
      })

      tree.addChild(mushroom)
    }
  }
}
