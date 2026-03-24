/**
 * TreeBuilder — Build a single tree entity from a Kenney GLB.
 *
 * Selects the correct GLB based on growth_stage + health from AssetManifest,
 * instances it via AssetLoader, scales by total_commits, and attaches
 * UserData for picking. Adds a billboard name label as a child, positioned
 * using the model's actual AABB height.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { EngineRepoData } from '../types'
import { AssetLoader } from '../assets/AssetLoader'
import { getTreeGLB } from '../assets/AssetManifest'
import { LabelRenderer } from '../rendering/LabelRenderer'
import { clamp, lerp } from '../utils/MathUtils'

/** Gap in model-space units between canopy top and label bottom. */
const LABEL_GAP = 0.25

export interface TreeResult {
  entity: pc.Entity
  repoName: string
  radius: number  // exclusion zone radius
  label: pc.Entity // billboard name label (child of entity)
}

export class TreeBuilder {
  private loader: AssetLoader

  constructor(loader: AssetLoader) {
    this.loader = loader
  }

  async build(app: Application, repo: EngineRepoData, x: number, z: number): Promise<TreeResult> {
    const glbPath = getTreeGLB(repo.growth_stage, repo.health)
    const asset = await this.loader.load(glbPath)
    const entity = this.loader.instance(asset)

    // Scale by total_commits — native trees are only 1.2–1.7 units tall, need scaling to be landmarks
    // Reduced from 8–15× to 5–9× to prevent canopy overlap in the orchard
    const commitScale = clamp(lerp(5.0, 9.0, Math.min(repo.total_commits / 500, 1)), 5.0, 9.0)
    entity.setLocalScale(commitScale, commitScale, commitScale)
    entity.setPosition(x, 0, z)
    entity.name = `Tree_${repo.repo_name}`

    // Attach pick data for interaction system
    const userData: Record<string, unknown> = {
      type: 'tree',
      repoName: repo.repo_name,
      health: repo.health,
      growthStage: repo.growth_stage,
      branchCount: repo.branches.length,
      totalFiles: repo.total_files,
      totalCommits: repo.total_commits,
    }
    // Store on the entity for the picker system
    entity.tags.add('pickable')
    ;(entity as unknown as Record<string, unknown>)._userData = userData

    // Measure actual model height via Mesh.aabb (model space, always valid)
    const modelHeight = TreeBuilder.getModelHeight(entity)

    // Create billboard label as child of the tree entity
    const label = LabelRenderer.create(app, repo.repo_name)
    // Position in model space: just above the canopy top
    label.setLocalPosition(0, modelHeight + LABEL_GAP, 0)
    // Counter-scale so the label has consistent world-space size regardless of tree scale
    const invScale = 1 / commitScale
    const baseScale = label.getLocalScale().clone()
    label.setLocalScale(baseScale.x * invScale, baseScale.y * invScale, baseScale.z * invScale)
    entity.addChild(label)

    // Exclusion zone: canopy width at this scale (trees are ~0.7 units wide natively)
    const radius = 0.7 * commitScale

    return { entity, repoName: repo.repo_name, radius, label }
  }

  /**
   * Get model-space height of a GLB entity using Mesh.aabb.
   * Same pattern as BuildingFactory.getEntityHeight() — always valid,
   * no scene graph or render pass required.
   */
  private static getModelHeight(entity: pc.Entity): number {
    const renders = entity.findComponents('render') as pc.RenderComponent[]
    const meshInstances = renders.flatMap((rc: pc.RenderComponent) => rc.meshInstances)
    let maxY = 0
    for (const mi of meshInstances) {
      const meshTop = mi.mesh.aabb.getMax().y
      if (meshTop > maxY) maxY = meshTop
    }
    return maxY
  }
}
