// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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

// Arc label constants
const LABEL_CANVAS_W = 512
const LABEL_CANVAS_H = 64
const LABEL_FONT_SIZE = 40
const LABEL_SCALE = 1.8
const LABEL_FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'

// ─── Types ───────────────────────────────────────

interface ArcLabel {
  entity: pc.Entity
  texture: pc.Texture
  material: pc.StandardMaterial
  entityIdA: string
  entityIdB: string
}

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
  private arcLabels: ArcLabel[] = []
  private titleToLabelIdx = new Map<string, number>()
  private highlightedTitle: string | null = null
  private cameraEntity: pc.Entity | null = null
  private app: pc.AppBase | null = null

  constructor(materials: MaterialFactory) {
    this.materials = materials
  }

  /** Set PlayCanvas app and camera for label creation and billboard rotation. */
  setContext(app: pc.AppBase, camera: pc.Entity): void {
    this.app = app
    this.cameraEntity = camera
  }

  /**
   * Scan node entities for features with the same title on different repos.
   * Creates arc entities and midpoint labels between each pair of clones.
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

        // Create a label (hidden by default — shown on hover/click)
        if (this.app) {
          const eA = nodeEntities.get(entityIds[0])
          const eB = nodeEntities.get(entityIds[1])
          if (eA && eB) {
            const label = this.createArcLabel(
              title, eA.getPosition(), eB.getPosition(),
              entityIds[0], entityIds[1],
            )
            graphRoot.addChild(label.entity)
            label.entity.enabled = false
            this.titleToLabelIdx.set(title, this.arcLabels.length)
            this.arcLabels.push(label)
          }
        }
      }
    }
  }

  /** Update arc + label positions during force simulation. */
  updatePositions(nodeEntities: Map<string, pc.Entity>): void {
    // Update arc segment positions
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

    // Update label positions + billboard rotation
    if (this.cameraEntity) {
      const camPos = this.cameraEntity.getPosition()
      for (const label of this.arcLabels) {
        if (!label.entity.enabled) continue
        const eA = nodeEntities.get(label.entityIdA)
        const eB = nodeEntities.get(label.entityIdB)
        if (eA && eB) {
          const pA = eA.getPosition()
          const pB = eB.getPosition()
          label.entity.setPosition(
            (pA.x + pB.x) / 2,
            (pA.y + pB.y) / 2 + CROSS_REPO_ARC_HEIGHT * 0.8,
            (pA.z + pB.z) / 2,
          )
        }
        label.entity.lookAt(camPos)
        label.entity.rotateLocal(90, 180, 0)
      }
    }
  }

  /** Toggle visibility of all cross-repo arcs. Labels are shown on hover only. */
  setVisible(visible: boolean): void {
    this.visible = visible
    for (const link of this.links) {
      for (const handle of link.edgeHandles) {
        handle.parent.enabled = visible
      }
    }
    // Hide all labels when arcs are hidden
    if (!visible) {
      for (const label of this.arcLabels) label.entity.enabled = false
      this.highlightedTitle = null
    }
  }

  /** Show label for a specific feature title (call on hover/click). null hides all. */
  showLabelForTitle(title: string | null): void {
    // Hide previous
    if (this.highlightedTitle) {
      const prevIdx = this.titleToLabelIdx.get(this.highlightedTitle)
      if (prevIdx !== undefined) this.arcLabels[prevIdx].entity.enabled = false
    }
    this.highlightedTitle = title
    // Show new
    if (title && this.visible) {
      const idx = this.titleToLabelIdx.get(title)
      if (idx !== undefined) this.arcLabels[idx].entity.enabled = true
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

  private createArcLabel(
    title: string,
    posA: pc.Vec3,
    posB: pc.Vec3,
    entityIdA: string,
    entityIdB: string,
  ): ArcLabel {
    // Strip "Feature: " prefix for shorter labels
    let displayTitle = title
    if (displayTitle.toLowerCase().startsWith('feature:')) {
      displayTitle = displayTitle.slice(8).trim()
    }
    // Truncate long titles
    if (displayTitle.length > 35) {
      displayTitle = displayTitle.slice(0, 33) + '…'
    }

    // Render text to canvas
    const canvas = document.createElement('canvas')
    canvas.width = LABEL_CANVAS_W
    canvas.height = LABEL_CANVAS_H
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Background pill
    ctx.fillStyle = 'rgba(20, 85, 95, 0.8)'
    ctx.beginPath()
    ctx.roundRect(4, 4, canvas.width - 8, canvas.height - 8, 12)
    ctx.fill()

    // Text
    ctx.font = `bold ${LABEL_FONT_SIZE}px ${LABEL_FONT}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#E0F7FA'
    ctx.fillText(displayTitle, canvas.width / 2, canvas.height / 2)

    // Upload as texture
    const texture = new pc.Texture(this.app!.graphicsDevice, {
      width: canvas.width,
      height: canvas.height,
      format: pc.PIXELFORMAT_RGBA8,
      mipmaps: true,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
    })
    texture.setSource(canvas)

    // CLAUDE.md exception: MaterialFactory doesn't support emissive/opacity map materials.
    // Manually created and destroyed in destroyArcs().
    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(0, 0, 0, 0)
    mat.emissiveMap = texture
    mat.emissive = new pc.Color(1, 1, 1)
    mat.opacityMap = texture
    mat.opacityMapChannel = 'a'
    mat.blendType = pc.BLEND_NORMAL
    mat.depthWrite = false
    mat.cull = pc.CULLFACE_NONE
    mat.update()

    // Plane entity
    const entity = new pc.Entity(`XRLabel_${title.slice(0, 20)}`)
    entity.addComponent('render', { type: 'plane' })
    entity.render!.meshInstances[0].material = mat

    const aspect = LABEL_CANVAS_W / LABEL_CANVAS_H
    entity.setLocalScale(LABEL_SCALE * aspect, LABEL_SCALE, 1)

    // Position at arc midpoint
    entity.setPosition(
      (posA.x + posB.x) / 2,
      (posA.y + posB.y) / 2 + CROSS_REPO_ARC_HEIGHT * 0.8,
      (posA.z + posB.z) / 2,
    )

    return { entity, texture, material: mat, entityIdA, entityIdB }
  }

  private destroyArcs(): void {
    for (const link of this.links) {
      for (const handle of link.edgeHandles) {
        handle.parent.destroy()
      }
    }
    for (const label of this.arcLabels) {
      label.entity.destroy()
      label.material.destroy()
      label.texture.destroy()
    }
    this.arcLabels = []
    this.titleToLabelIdx.clear()
    this.highlightedTitle = null
    this.links = []
  }
}
