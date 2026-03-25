/**
 * GraphCrossRepoSystem — detects and visualizes features that span multiple repos.
 *
 * When a feature is linked to multiple repos (via KnowledgeRepoLink), the backend
 * emits duplicate FeatureItem entries with the same title but different repo_name.
 * This system detects those duplicates and draws dashed-style cyan arcs between them,
 * making cross-repo scope visible at a glance.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { EdgeHandle } from './GraphEdgeBuilder'
import { getGraphData } from './GraphNodeData'
import { ArcBuilder } from './ArcBuilder'

// ─── Constants ───────────────────────────────────

const CROSS_REPO_COLOR: [number, number, number] = [0.2, 0.85, 0.95]
const CROSS_REPO_OPACITY = 0.6
const CROSS_REPO_ARC_HEIGHT = 1.5
const CROSS_REPO_THICKNESS = 0.025

// ─── Types ───────────────────────────────────────

interface CrossRepoLink {
  title: string
  entityIds: string[]
  edgeHandles: EdgeHandle[]
}

// ─── System ──────────────────────────────────────

export class GraphCrossRepoSystem {
  private materials: MaterialFactory
  private links: CrossRepoLink[] = []
  private visible = true
  private matKey: string | null = null
  // O(1) lookup: feature title → repo count
  private repoCountMap = new Map<string, number>()
  private arc = new ArcBuilder()

  constructor(materials: MaterialFactory) {
    this.materials = materials
  }

  /**
   * Scan node entities for features with the same title on different repos.
   * Creates arc entities between each pair of clones.
   */
  build(
    nodeEntities: Map<string, pc.Entity>,
    graphRoot: pc.Entity,
  ): void {
    this.destroyArcs()
    this.repoCountMap.clear()

    // Group feature entity IDs by title
    const titleToIds = new Map<string, string[]>()
    for (const [entityId, entity] of nodeEntities) {
      const data = getGraphData(entity)
      if (!data || data.type !== 'graph_feature') continue
      const arr = titleToIds.get(data.title)
      if (arr) arr.push(entityId)
      else titleToIds.set(data.title, [entityId])
    }

    // Create a single shared material for all cross-repo arcs
    this.matKey = 'gn_cross_repo'
    const mat = this.materials.getColor(
      this.matKey,
      CROSS_REPO_COLOR[0],
      CROSS_REPO_COLOR[1],
      CROSS_REPO_COLOR[2],
      {
        metalness: 0,
        gloss: 0.4,
        opacity: CROSS_REPO_OPACITY,
        emissive: [
          CROSS_REPO_COLOR[0] * 0.4,
          CROSS_REPO_COLOR[1] * 0.4,
          CROSS_REPO_COLOR[2] * 0.4,
        ],
      },
    )

    // Build arcs for features appearing on 2+ repos
    for (const [title, entityIds] of titleToIds) {
      if (entityIds.length < 2) continue

      const edgeHandles: EdgeHandle[] = []

      // Connect all pairs (for 2 clones = 1 arc, for 3 = 3 arcs, etc.)
      for (let i = 0; i < entityIds.length; i++) {
        for (let j = i + 1; j < entityIds.length; j++) {
          const entityA = nodeEntities.get(entityIds[i])
          const entityB = nodeEntities.get(entityIds[j])
          if (!entityA || !entityB) continue

          const posA = entityA.getPosition()
          const posB = entityB.getPosition()
          const handle = this.buildArc(posA, posB, `xr_${entityIds[i]}__${entityIds[j]}`, mat)
          graphRoot.addChild(handle.parent)
          handle.parent.enabled = this.visible
          edgeHandles.push(handle)
        }
      }

      if (edgeHandles.length > 0) {
        this.links.push({ title, entityIds, edgeHandles })
        this.repoCountMap.set(title, entityIds.length)
      }
    }
  }

  /** Update arc positions during force simulation (features move with repos). */
  updatePositions(nodeEntities: Map<string, pc.Entity>): void {
    for (const link of this.links) {
      let handleIdx = 0
      for (let i = 0; i < link.entityIds.length; i++) {
        for (let j = i + 1; j < link.entityIds.length; j++) {
          const handle = link.edgeHandles[handleIdx++]
          if (!handle) continue

          const entityA = nodeEntities.get(link.entityIds[i])
          const entityB = nodeEntities.get(link.entityIds[j])
          if (!entityA || !entityB) continue

          this.updateArc(handle, entityA.getPosition(), entityB.getPosition())
        }
      }
    }
  }

  /** Toggle visibility of all cross-repo arcs. */
  setVisible(visible: boolean): void {
    this.visible = visible
    for (const link of this.links) {
      for (const handle of link.edgeHandles) {
        handle.parent.enabled = visible
      }
    }
  }

  /** Check if cross-repo links are currently visible. */
  isVisible(): boolean {
    return this.visible
  }

  /** Get all cross-repo link data (for tooltips/detail panel). */
  getLinks(): ReadonlyArray<{ title: string; repoCount: number }> {
    return this.links.map((l) => ({ title: l.title, repoCount: l.entityIds.length }))
  }

  /** Check if a feature title spans multiple repos. O(1) lookup. */
  getRepoCount(title: string): number {
    return this.repoCountMap.get(title) ?? 1
  }

  /** Destroy all arc entities and release materials. */
  destroy(): void {
    this.destroyArcs()
    if (this.matKey) {
      this.materials.release(this.matKey)
      this.matKey = null
    }
  }

  // ─── Private: Arc Construction ─────────────────

  private buildArc(
    from: pc.Vec3,
    to: pc.Vec3,
    edgeId: string,
    mat: pc.StandardMaterial,
  ): EdgeHandle {
    const parent = new pc.Entity(`XR_${edgeId}`)
    const segments = this.arc.buildSegments(
      from, to, CROSS_REPO_ARC_HEIGHT, CROSS_REPO_THICKNESS, mat, parent, 'XRS',
    )
    return { parent, segments, sourceId: edgeId.split('__')[0], targetId: edgeId.split('__')[1] }
  }

  private updateArc(handle: EdgeHandle, from: pc.Vec3, to: pc.Vec3): void {
    this.arc.updateSegments(handle.segments, from, to, CROSS_REPO_ARC_HEIGHT, CROSS_REPO_THICKNESS)
  }

  private destroyArcs(): void {
    for (const link of this.links) {
      for (const handle of link.edgeHandles) {
        handle.parent.destroy()
      }
    }
    this.links = []
  }
}
