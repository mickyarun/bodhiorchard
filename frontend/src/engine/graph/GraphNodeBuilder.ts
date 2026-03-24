/**
 * GraphNodeBuilder — creates PlayCanvas sphere entities for graph nodes.
 *
 * Each repo gets a unique vibrant color from a palette. Feature nodes
 * inherit a lighter tint of their parent repo's color.
 *
 * Both are tagged 'pickable' with _userData for raycasting identification.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { EngineRepoData, EngineFeature } from '../types'

// ─── Distinct Repo Colors (vibrant palette) ─────

const REPO_PALETTE: [number, number, number][] = [
  [0.95, 0.26, 0.21],  // Red
  [0.13, 0.59, 0.95],  // Blue
  [0.30, 0.69, 0.31],  // Green
  [1.00, 0.60, 0.00],  // Orange
  [0.61, 0.15, 0.69],  // Purple
  [0.00, 0.74, 0.83],  // Teal
  [0.96, 0.49, 0.00],  // Deep Orange
  [0.55, 0.76, 0.29],  // Light Green
  [0.25, 0.32, 0.71],  // Indigo
  [0.94, 0.76, 0.06],  // Yellow
  [0.85, 0.11, 0.38],  // Pink
  [0.00, 0.59, 0.53],  // Teal dark
  [0.47, 0.33, 0.28],  // Brown
  [0.38, 0.49, 0.55],  // Blue Grey
  [0.62, 0.01, 0.01],  // Dark Red
  [0.10, 0.28, 0.45],  // Navy
]

// Distinct colors for feature dots (different from repo palette)
const FEATURE_PALETTE: [number, number, number][] = [
  [1.00, 0.92, 0.23],  // Yellow
  [0.00, 0.90, 0.46],  // Emerald
  [0.39, 0.71, 1.00],  // Sky Blue
  [1.00, 0.44, 0.37],  // Coral
  [0.73, 0.55, 1.00],  // Lavender
  [1.00, 0.70, 0.28],  // Amber
  [0.26, 0.96, 0.84],  // Mint
  [1.00, 0.47, 0.66],  // Pink
  [0.56, 0.93, 0.56],  // Light Green
  [0.82, 0.68, 1.00],  // Mauve
  [1.00, 0.84, 0.40],  // Gold
  [0.40, 0.85, 0.94],  // Cyan
]

// ─── Scales ─────────────────────────────────────

const REPO_SCALE = 2.5
const FEATURE_SCALE = 1.0

// ─── Builder ────────────────────────────────────

export class GraphNodeBuilder {
  private materials: MaterialFactory
  private repoColorMap = new Map<string, [number, number, number]>()
  private matKeysUsed = new Set<string>()

  constructor(materials: MaterialFactory) {
    this.materials = materials
  }

  /** Assign a unique color to each repo. Call before building nodes. */
  assignRepoColors(repoNames: string[]): void {
    this.repoColorMap.clear()
    for (let i = 0; i < repoNames.length; i++) {
      this.repoColorMap.set(repoNames[i], REPO_PALETTE[i % REPO_PALETTE.length])
    }
  }

  /** Get assigned color for a repo. */
  getRepoColor(repoName: string): [number, number, number] {
    return this.repoColorMap.get(repoName) ?? REPO_PALETTE[0]
  }

  /** Create a repo node entity. */
  buildRepoNode(repo: EngineRepoData): pc.Entity {
    const entity = new pc.Entity(`GN_Repo_${repo.repo_name}`)
    entity.addComponent('render', { type: 'sphere' })
    entity.setLocalScale(REPO_SCALE, REPO_SCALE, REPO_SCALE)

    const color = this.getRepoColor(repo.repo_name)
    const matKey = `gn_repo_${repo.repo_name}`
    this.matKeysUsed.add(matKey)
    const mat = this.materials.getColor(matKey, color[0], color[1], color[2], {
      metalness: 0.35,
      gloss: 0.7,
      emissive: [color[0] * 0.15, color[1] * 0.15, color[2] * 0.15],
    })
    entity.render!.meshInstances[0].material = mat

    entity.tags.add('pickable')
    ;(entity as unknown as Record<string, unknown>)._userData = {
      type: 'graph_repo',
      repoName: repo.repo_name,
      health: repo.health,
      growthStage: repo.growth_stage,
      totalFiles: repo.total_files,
      totalCommits: repo.total_commits,
    }

    return entity
  }

  /** Create a feature node entity — each feature gets a unique vibrant color. */
  buildFeatureNode(feature: EngineFeature, index: number): pc.Entity {
    const entity = new pc.Entity(`GN_Feat_${index}_${feature.title.slice(0, 20)}`)
    entity.addComponent('render', { type: 'sphere' })
    entity.setLocalScale(FEATURE_SCALE, FEATURE_SCALE, FEATURE_SCALE)

    // Each feature gets a distinct color from the feature palette
    const color = FEATURE_PALETTE[index % FEATURE_PALETTE.length]

    const matKey = `gn_feat_${feature.repo_name ?? 'none'}_${index}`
    this.matKeysUsed.add(matKey)
    const mat = this.materials.getColor(matKey, color[0], color[1], color[2], {
      metalness: 0.1,
      gloss: 0.5,
      emissive: [color[0] * 0.2, color[1] * 0.2, color[2] * 0.2],
    })
    entity.render!.meshInstances[0].material = mat

    entity.tags.add('pickable')
    ;(entity as unknown as Record<string, unknown>)._userData = {
      type: 'graph_feature',
      title: feature.title,
      status: feature.status,
      repoName: feature.repo_name,
      sourceRef: feature.source_ref,
      fromBud: feature.from_bud,
      branchName: feature.branch_name,
    }

    return entity
  }

  /** Release all materials created by this builder. */
  destroy(): void {
    for (const key of this.matKeysUsed) {
      this.materials.release(key)
    }
    this.matKeysUsed.clear()
    this.repoColorMap.clear()
  }
}
