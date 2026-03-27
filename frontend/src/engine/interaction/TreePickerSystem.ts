/**
 * TreePickerSystem — raycasting, hover tooltips, and click handling for tree-world entities.
 *
 * Uses ray-sphere intersection against entities tagged 'pickable'.
 * Reads typed TreeNodeData via the discriminated union accessor.
 *
 * Pattern source: engine/graph/GraphPickingSystem.ts
 */
import * as pc from 'playcanvas'
import type { InputManager } from '../input/InputManager'
import type { EngineCallbacks, RepoHealth } from '../types'
import { getTreeData, type TreeNodeData } from '../world/TreeNodeData'

/** Optional function to enrich hover tooltip text (e.g. add cross-repo count). */
export type TreeTooltipEnricher = (data: TreeNodeData, baseText: string) => string

export class TreePickerSystem {
  private lastHoveredId: string | null = null
  private lastHoverPos = { x: -1, y: -1 }
  private tooltipEnricher: TreeTooltipEnricher | null = null

  // Pre-allocated scratch vectors for raycasting
  private readonly _rayFrom = new pc.Vec3()
  private readonly _rayTo = new pc.Vec3()
  private readonly _rayDir = new pc.Vec3()

  /** Set optional tooltip enricher (called after base tooltip text is computed). */
  setTooltipEnricher(enricher: TreeTooltipEnricher | null): void {
    this.tooltipEnricher = enricher
  }

  /** Run picking for one frame. */
  update(
    camera: pc.Entity,
    input: InputManager,
    pickableEntities: pc.Entity[],
    callbacks: EngineCallbacks,
  ): void {
    const click = input.consumeClick()
    const hoverPos = input.getHoverPos()

    if (click) {
      const hit = this.raycast(camera, click.x, click.y, pickableEntities)
      if (hit) this.handleClick(hit, callbacks)
    }

    // Hover — skip if mouse hasn't moved
    if (hoverPos.x === this.lastHoverPos.x && hoverPos.y === this.lastHoverPos.y) return
    this.lastHoverPos.x = hoverPos.x
    this.lastHoverPos.y = hoverPos.y

    const hit = this.raycast(camera, hoverPos.x, hoverPos.y, pickableEntities)
    if (hit) {
      this.handleHover(hit, hoverPos, callbacks)
    } else if (this.lastHoveredId) {
      this.lastHoveredId = null
      callbacks.onHover?.(null)
    }
  }

  // ─── Click Handler ─────────────────────────────

  private handleClick(entity: pc.Entity, callbacks: EngineCallbacks): void {
    const data = getTreeData(entity)
    if (!data) return

    switch (data.type) {
      case 'tree_repo':
        callbacks.onTreeClick?.({
          repoName: data.repoName,
          health: data.health as RepoHealth,
          growthStage: data.growthStage,
          branchCount: data.branchCount,
          totalFiles: data.totalFiles,
          totalCommits: data.totalCommits,
        })
        break
      case 'tree_feature':
        callbacks.onFeatureClick?.({
          title: data.title,
          status: data.status,
          repoName: data.repoName,
          linkedRepos: data.linkedRepos,
          codeLocations: data.codeLocations,
          branchName: data.branchName,
          fromBud: data.fromBud,
          sourceRef: data.sourceRef,
        })
        break
    }
  }

  // ─── Hover Handler ─────────────────────────────

  private handleHover(
    entity: pc.Entity,
    hoverPos: { x: number; y: number },
    callbacks: EngineCallbacks,
  ): void {
    const data = getTreeData(entity)
    if (!data) return

    const nodeId = this.getNodeId(data)
    if (nodeId === this.lastHoveredId) return

    this.lastHoveredId = nodeId
    let text = this.getTooltipText(data)

    if (this.tooltipEnricher) {
      text = this.tooltipEnricher(data, text)
    }

    callbacks.onHover?.({ text, screenX: hoverPos.x, screenY: hoverPos.y })
  }

  private getNodeId(data: TreeNodeData): string {
    switch (data.type) {
      case 'tree_repo': return `repo_${data.repoName}`
      case 'tree_feature': return `feat_${data.title}`
      case 'tree_bud': return `bud_${data.budNumber}`
      case 'tree_threat': return `threat_${data.id}`
      case 'tree_relationship': return `rel_${data.sourceRepo}_${data.targetRepo}`
    }
  }

  private getTooltipText(data: TreeNodeData): string {
    switch (data.type) {
      case 'tree_repo':
        return `${data.repoName} (${data.health})`
      case 'tree_feature':
        return `${data.title}\n[${data.status}]`
      case 'tree_bud':
        return `BUD #${data.budNumber}: ${data.title} [${data.status}]`
      case 'tree_threat':
        return `⚠ ${data.title} (${data.severity})`
      case 'tree_relationship':
        return `${data.sourceRepo} → ${data.targetRepo} [${data.relType}]`
    }
  }

  // ─── Raycasting ────────────────────────────────

  private raycast(
    camera: pc.Entity,
    screenX: number,
    screenY: number,
    pickableEntities: pc.Entity[],
  ): pc.Entity | null {
    const cam = camera.camera
    if (!cam) return null

    cam.screenToWorld(screenX, screenY, cam.nearClip, this._rayFrom)
    cam.screenToWorld(screenX, screenY, cam.farClip, this._rayTo)
    this._rayDir.sub2(this._rayTo, this._rayFrom).normalize()

    let closestEntity: pc.Entity | null = null
    let closestDist = Infinity

    for (const entity of pickableEntities) {
      if (!entity.tags.has('pickable')) continue
      const pos = entity.getPosition()
      const scale = entity.getLocalScale()
      // Inflated pick radius for small fruits (1.5× visual radius)
      const radius = Math.max(scale.x, scale.y, scale.z) / 2 * 1.5
      const dist = this.raySphereIntersect(this._rayFrom, this._rayDir, pos, radius)
      if (dist !== null && dist < closestDist) {
        closestDist = dist
        closestEntity = entity
      }
    }

    return closestEntity
  }

  private raySphereIntersect(
    origin: pc.Vec3,
    dir: pc.Vec3,
    center: pc.Vec3,
    radius: number,
  ): number | null {
    const ox = origin.x - center.x
    const oy = origin.y - center.y
    const oz = origin.z - center.z
    const a = dir.x * dir.x + dir.y * dir.y + dir.z * dir.z
    const b = 2 * (ox * dir.x + oy * dir.y + oz * dir.z)
    const c = ox * ox + oy * oy + oz * oz - radius * radius
    const discriminant = b * b - 4 * a * c
    if (discriminant < 0) return null
    const t = (-b - Math.sqrt(discriminant)) / (2 * a)
    return t > 0 ? t : null
  }
}
