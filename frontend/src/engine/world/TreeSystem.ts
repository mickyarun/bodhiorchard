/**
 * TreeSystem — Orchestrator for all repo trees.
 *
 * Takes EngineData.repos, builds all trees via TreeBuilder, decorates
 * them via TreeDecorator, and places them using WorldLayout positions.
 * Returns exclusion zones for scatter systems.
 *
 * Uses pre-indexed Maps for O(1) feature/bud/threat lookup per repo,
 * instead of O(repos * items) filtering.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { EngineData, EngineFeature, EngineBUD, EngineThreat } from '../types'
import { AssetLoader } from '../assets/AssetLoader'
import { WorldLayout } from './WorldLayout'
import { TreeBuilder, type TreeResult } from './TreeBuilder'
import { TreeDecorator } from './TreeDecorator'
import { LabelRenderer } from '../rendering/LabelRenderer'
import type { RepoVisualization } from './RepoVisualization'
import type { ExclusionZone } from '../utils/MathUtils'

export class TreeSystem implements RepoVisualization {
  private app: Application | null = null
  private root: pc.Entity | null = null
  private builder: TreeBuilder
  private decorator: TreeDecorator
  private trees: TreeResult[] = []
  private treeMap = new Map<string, pc.Entity>()

  constructor(loader: AssetLoader) {
    this.builder = new TreeBuilder(loader)
    this.decorator = new TreeDecorator(loader)
  }

  async build(
    app: Application,
    data: EngineData,
    layout: WorldLayout,
  ): Promise<ExclusionZone[]> {
    this.app = app
    this.root = new pc.Entity('TreeSystem')
    this.trees = []
    this.treeMap.clear()

    const positions = layout.getTreePositions(data.repos.length)
    const exclusionZones: ExclusionZone[] = []

    // Pre-index features, buds, threats by repo_name for O(1) lookup
    const featuresByRepo = new Map<string, EngineFeature[]>()
    for (const f of data.features) {
      const key = f.repo_name ?? ''
      const arr = featuresByRepo.get(key)
      if (arr) arr.push(f); else featuresByRepo.set(key, [f])
    }

    const budsByRepo = new Map<string, EngineBUD[]>()
    for (const b of data.buds) {
      const key = b.repo_name ?? ''
      const arr = budsByRepo.get(key)
      if (arr) arr.push(b); else budsByRepo.set(key, [b])
    }

    // Index threats by branch_name for efficient lookup
    const threatsByBranch = new Map<string, EngineThreat[]>()
    for (const t of data.threats) {
      const key = t.branch_name ?? ''
      const arr = threatsByBranch.get(key)
      if (arr) arr.push(t); else threatsByBranch.set(key, [t])
    }

    // Build all trees (each tree includes its own name label as a child)
    for (let i = 0; i < data.repos.length; i++) {
      const repo = data.repos[i]
      const pos = positions[i]
      const result = await this.builder.build(app, repo, pos.x, pos.z)
      this.root.addChild(result.entity)
      this.trees.push(result)
      this.treeMap.set(repo.repo_name, result.entity)

      exclusionZones.push({ x: pos.x, z: pos.z, radius: result.radius })
    }

    // Decorate trees with features, buds, threats
    for (const repo of data.repos) {
      const treeEntity = this.treeMap.get(repo.repo_name)
      if (!treeEntity) continue

      const repoFeatures = featuresByRepo.get(repo.repo_name) ?? []
      if (repoFeatures.length > 0) {
        await this.decorator.decorateFeatures(treeEntity, repoFeatures)
      }

      const repoBuds = budsByRepo.get(repo.repo_name) ?? []
      if (repoBuds.length > 0) {
        await this.decorator.decorateBuds(treeEntity, repoBuds)
      }

      // Collect threats matching any branch of this repo
      const repoThreats: EngineThreat[] = []
      for (const branch of repo.branches) {
        const branchThreats = threatsByBranch.get(branch.name)
        if (branchThreats) repoThreats.push(...branchThreats)
      }
      if (repoThreats.length > 0) {
        await this.decorator.decorateThreats(treeEntity, repoThreats)
      }
    }

    app.root.addChild(this.root)
    return exclusionZones
  }

  getTreePosition(repoName: string): pc.Vec3 | null {
    const entity = this.treeMap.get(repoName)
    if (!entity) return null
    return entity.getPosition().clone()
  }

  getTreeEntity(repoName: string): pc.Entity | undefined {
    return this.treeMap.get(repoName)
  }

  getAllTrees(): readonly TreeResult[] {
    return this.trees
  }

  destroy(): void {
    // Unregister billboard labels + free GPU resources before root.destroy() handles entities
    if (this.app) {
      for (const tree of this.trees) {
        LabelRenderer.cleanup(this.app, tree.label)
      }
    }

    if (this.root) {
      this.root.destroy()
      this.root = null
    }
    this.trees = []
    this.treeMap.clear()
    this.app = null
  }
}
