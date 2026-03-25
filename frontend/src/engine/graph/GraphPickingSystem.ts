/**
 * GraphPickingSystem — raycasting, hover tooltips, and click handling.
 *
 * Uses ray-sphere intersection against pickable entities.
 * Reads typed GraphNodeData via the discriminated union accessor.
 */
import * as pc from 'playcanvas'
import type { InputManager } from '../input/InputManager'
import { getGraphData } from './GraphNodeData'
import type { GraphNodeData } from './GraphNodeData'
import type { GraphCallbacks } from './GraphTypes'

/** Optional function to enrich hover tooltip text (e.g. add cross-repo count). */
export type TooltipEnricher = (data: GraphNodeData, baseText: string) => string

export class GraphPickingSystem {
  private lastHoveredId: string | null = null
  private lastHoverPos = { x: -1, y: -1 }
  private tooltipEnricher: TooltipEnricher | null = null

  // Pre-allocated scratch vectors for raycasting
  private readonly _rayFrom = new pc.Vec3()
  private readonly _rayTo = new pc.Vec3()
  private readonly _rayDir = new pc.Vec3()

  /** Set optional tooltip enricher (called after base tooltip text is computed). */
  setTooltipEnricher(enricher: TooltipEnricher | null): void {
    this.tooltipEnricher = enricher
  }

  /** Run picking for one frame. */
  update(
    camera: pc.Entity,
    input: InputManager,
    nodeEntities: Map<string, pc.Entity>,
    callbacks: GraphCallbacks,
  ): void {
    const click = input.consumeClick()
    const hoverPos = input.getHoverPos()

    if (click) {
      const hit = this.raycast(camera, click.x, click.y, nodeEntities)
      if (hit) this.handleClick(hit, callbacks)
    }

    // Hover — skip if mouse hasn't moved
    if (hoverPos.x === this.lastHoverPos.x && hoverPos.y === this.lastHoverPos.y) return
    this.lastHoverPos.x = hoverPos.x
    this.lastHoverPos.y = hoverPos.y

    const hit = this.raycast(camera, hoverPos.x, hoverPos.y, nodeEntities)
    if (hit) {
      this.handleHover(hit, hoverPos, callbacks)
    } else if (this.lastHoveredId) {
      this.lastHoveredId = null
      callbacks.onHover?.(null)
    }
  }

  // ─── Click Handler ─────────────────────────────

  private handleClick(entity: pc.Entity, callbacks: GraphCallbacks): void {
    const data = getGraphData(entity)
    if (!data) return

    if (data.type === 'graph_repo') {
      callbacks.onRepoClick?.({
        repoName: data.repoName,
        health: data.health,
        growthStage: data.growthStage,
        totalFiles: data.totalFiles,
        totalCommits: data.totalCommits,
      })
    } else {
      callbacks.onFeatureClick?.({
        title: data.title,
        status: data.status,
        repoName: data.repoName,
        sourceRef: data.sourceRef,
        fromBud: data.fromBud,
        branchName: data.branchName,
        linkedRepos: data.linkedRepos,
        codeLocations: data.codeLocations,
      })
    }
  }

  // ─── Hover Handler ─────────────────────────────

  private handleHover(
    entity: pc.Entity,
    hoverPos: { x: number; y: number },
    callbacks: GraphCallbacks,
  ): void {
    const data = getGraphData(entity)
    if (!data) return

    const nodeId = data.type === 'graph_repo' ? data.repoName : data.title
    if (nodeId === this.lastHoveredId) return

    this.lastHoveredId = nodeId
    let text =
      data.type === 'graph_repo'
        ? `${data.repoName} (${data.health})`
        : `${data.title}\n[${data.status}]`

    if (this.tooltipEnricher) {
      text = this.tooltipEnricher(data, text)
    }

    callbacks.onHover?.({ text, screenX: hoverPos.x, screenY: hoverPos.y })
  }

  // ─── Raycasting ────────────────────────────────

  private raycast(
    camera: pc.Entity,
    screenX: number,
    screenY: number,
    nodeEntities: Map<string, pc.Entity>,
  ): pc.Entity | null {
    const cam = camera.camera
    if (!cam) return null

    cam.screenToWorld(screenX, screenY, cam.nearClip, this._rayFrom)
    cam.screenToWorld(screenX, screenY, cam.farClip, this._rayTo)
    this._rayDir.sub2(this._rayTo, this._rayFrom).normalize()

    let closestEntity: pc.Entity | null = null
    let closestDist = Infinity

    for (const [, entity] of nodeEntities) {
      if (!entity.tags.has('pickable')) continue
      const pos = entity.getPosition()
      const scale = entity.getLocalScale()
      const radius = Math.max(scale.x, scale.y, scale.z) / 2
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
