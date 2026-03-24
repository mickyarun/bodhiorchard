/**
 * TreeBuilder — Build a single tree entity from a Kenney GLB.
 *
 * Selects the correct GLB based on growth_stage + health from AssetManifest,
 * instances it via AssetLoader, scales by total_commits, and attaches
 * UserData for picking.
 */
import * as pc from 'playcanvas'
import type { EngineRepoData } from '../types'
import { AssetLoader } from '../assets/AssetLoader'
import { getTreeGLB } from '../assets/AssetManifest'
import { clamp, lerp } from '../utils/MathUtils'

export interface TreeResult {
  entity: pc.Entity
  repoName: string
  radius: number // exclusion zone radius
}

export class TreeBuilder {
  private loader: AssetLoader

  constructor(loader: AssetLoader) {
    this.loader = loader
  }

  async build(repo: EngineRepoData, x: number, z: number): Promise<TreeResult> {
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

    // Exclusion zone: canopy width at this scale (trees are ~0.7 units wide natively)
    const radius = 0.7 * commitScale

    return { entity, repoName: repo.repo_name, radius }
  }
}
