/**
 * TreePickerSystem — hover tooltips and click handling for tree-world entities.
 *
 * Two picking primitives:
 *   • Feature branches (tall thin cylinders) → 2D screen-space distance.
 *     Matches the reference pattern in treetest/index.ts — ray-sphere fails on
 *     branches because their pick sphere at entity origin is a blob at the
 *     base, missing the branch length where the user actually hovers.
 *   • Everything else (repo trees, houses, agents) → 3D ray-sphere.
 *     These have meaningful roughly-spherical bounds.
 *
 * Reads typed TreeNodeData via the discriminated union accessor.
 * Pattern source (ray path): engine/graph/GraphPickingSystem.ts
 * Pattern source (screen path): engine/treetest/index.ts onMouseMove
 */
import * as pc from 'playcanvas'
import type { InputManager } from '../input/InputManager'
import type { EngineCallbacks, RepoHealth } from '../types'
import { getTreeData, type TreeNodeData } from '../world/TreeNodeData'

/** Optional function to enrich hover tooltip text (e.g. add cross-repo count). */
export type TreeTooltipEnricher = (data: TreeNodeData, baseText: string) => string

/** Pixel radius within which a hover registers on a projected feature-branch point. */
const FEATURE_HOVER_PX = 18

export class TreePickerSystem {
  private lastHoveredId: string | null = null
  private lastHoverPos = { x: -1, y: -1 }
  private tooltipEnricher: TreeTooltipEnricher | null = null

  // Pre-allocated scratch vectors for raycasting + screen projection
  private readonly _rayFrom = new pc.Vec3()
  private readonly _rayTo = new pc.Vec3()
  private readonly _rayDir = new pc.Vec3()
  private readonly _scratchCenter = new pc.Vec3()
  private readonly _screenPos = new pc.Vec3()

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

    // Phase 1: feature branches by 2D screen-space distance (treetest-style).
    // Branches are thin cylinders — a ray-sphere at their origin misses the
    // branch body where the user actually hovers.
    let hit = this.pickFeatureByScreen(camera, hoverPos.x, hoverPos.y, pickableEntities)
    // Phase 2: fall back to ray-sphere for chunkier entities (repo, house, agent, bud, threat, rel).
    if (!hit) hit = this.raycast(camera, hoverPos.x, hoverPos.y, pickableEntities)

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
      case 'tree_house':
        callbacks.onHouseClick?.({
          memberId: data.memberId,
          name: data.memberName,
          activity: 'home',
        })
        break
      case 'tree_agent':
        callbacks.onAgentClick?.({
          agentKey: data.agentKey,
          skillSlug: data.skillSlug,
          skillName: data.skillName,
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
      case 'tree_house': return `house_${data.memberId}`
      case 'tree_agent': return `agent_${data.agentKey}`
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
      case 'tree_house':
        return `Enter ${data.memberName}'s house`
      case 'tree_agent':
        return `${data.skillName} (busy)`
    }
  }

  // ─── Screen-space feature picking ──────────────

  /**
   * 2D screen-space picker for feature branches.
   * Projects every tree_feature entity's world position into screen space
   * and returns the closest one within FEATURE_HOVER_PX of the cursor.
   *
   * Why not ray-sphere: feature branches are thin cylinders. entity.getPosition()
   * is at the base with scale.y encoding length — a ray-sphere at max(scale)/2
   * gives a small blob near the base that misses the visible branch body.
   *
   * Mirrors treetest/index.ts:241-273.
   */
  private pickFeatureByScreen(
    camera: pc.Entity,
    screenX: number,
    screenY: number,
    pickableEntities: pc.Entity[],
  ): pc.Entity | null {
    const cam = camera.camera
    if (!cam) return null

    let best: pc.Entity | null = null
    let bestDist = FEATURE_HOVER_PX * FEATURE_HOVER_PX

    for (const entity of pickableEntities) {
      if (!entity.tags.has('pickable')) continue
      const data = getTreeData(entity)
      if (data?.type !== 'tree_feature') continue

      cam.worldToScreen(entity.getPosition(), this._screenPos)
      // screenPos.z < 0 means behind the camera — skip
      if (this._screenPos.z < 0) continue
      const dx = this._screenPos.x - screenX
      const dy = this._screenPos.y - screenY
      const d2 = dx * dx + dy * dy
      if (d2 < bestDist) {
        bestDist = d2
        best = entity
      }
    }

    return best
  }

  // ─── Ray-sphere picking (chunky entities + click fallback) ───

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
      let pos = entity.getPosition()
      const data = getTreeData(entity)
      // Houses are 4×4 tile buildings rotated 90°. The entity origin is at
      // the corner, not the visual center. Offset the pick sphere center to
      // match where the user sees the house. Radius 4 covers the full footprint.
      let radius: number
      if (data?.type === 'tree_house') {
        radius = 4
      } else if (data?.type === 'tree_agent') {
        radius = 1.5
        this._scratchCenter.copy(pos)
        this._scratchCenter.y += 0.6
        pos = this._scratchCenter
      } else if (data?.type === 'tree_repo') {
        // Repo tree containers sit at ground level with scale (1,1,1) but
        // the visual tree (trunk + canopy) extends 5-10 units up. Use a
        // generous sphere centered at mid-height to cover the full tree.
        radius = 6
        this._scratchCenter.copy(pos)
        this._scratchCenter.y += 4 // mid-height of typical tree
        pos = this._scratchCenter
      } else {
        const scale = entity.getLocalScale()
        radius = Math.max(scale.x, scale.y, scale.z) / 2 * 1.5
      }
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
