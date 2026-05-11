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
 * GraphOverlaySystem — visual overlays for bus factor, developer highlight, and status colors.
 *
 * Bus factor rings: flat disc child entities on features with few skilled developers.
 *   - 1 developer = red ring (critical bus factor)
 *   - 2 developers = yellow ring (warning)
 *   - 3+ developers = no ring (healthy)
 *
 * Developer highlight: glow ring on all features a developer is skilled in.
 * Uses GraphDimSystem to fade unrelated nodes.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { EngineFeatureSkill, EngineThreat, EngineBUD } from '../types'
import { getGraphData } from './GraphNodeData'
import { GraphDimSystem } from './GraphDimSystem'

// ─── Constants ───────────────────────────────────

// Halo sphere slightly larger than feature sphere (FEATURE_SCALE = 1.0)
const HALO_SCALE = 1.5
const HALO_Y_OFFSET = 0

const BUS_1_COLOR: [number, number, number] = [0.95, 0.2, 0.2]   // Red
const BUS_2_COLOR: [number, number, number] = [0.95, 0.85, 0.15]  // Yellow
const HIGHLIGHT_COLOR: [number, number, number] = [0.2, 0.9, 0.5] // Green glow

// Status overlay colors
const STATUS_COLORS: Record<string, [number, number, number]> = {
  planned: [0.25, 0.55, 0.95],
  in_progress: [1.0, 0.65, 0.0],
  implemented: [0.3, 0.78, 0.3],
}

// Threat overlay
const THREAT_HALO_COLOR: [number, number, number] = [1.0, 0.1, 0.1]

// BUD lifecycle badge
const BADGE_CANVAS_W = 128
const BADGE_CANVAS_H = 64
const BADGE_FONT_SIZE = 36
const BADGE_SCALE = 0.8
const BADGE_Y_OFFSET = -1.0

const BUD_STAGE_LABEL: Record<string, string> = {
  bud: 'BUD',
  design: 'DES',
  development: 'DEV',
  testing: 'TST',
  uat: 'UAT',
  prod: 'PROD',
  closed: 'DONE',
  discarded: '---',
}

const BUD_STAGE_COLOR: Record<string, string> = {
  bud: '#42A5F5',
  design: '#5C6BC0',
  development: '#FFA726',
  testing: '#FF7043',
  uat: '#AB47BC',
  prod: '#66BB6A',
  closed: '#78909C',
  discarded: '#616161',
}

// ─── System ──────────────────────────────────────

export class GraphOverlaySystem {
  private materials: MaterialFactory
  private dimSystem: GraphDimSystem
  private matKeys: string[] = []

  // Bus factor ring entities (keyed by feature entity ID)
  private busRings = new Map<string, pc.Entity>()
  private busFactorVisible = false

  // Developer highlight rings
  private highlightRings: pc.Entity[] = []
  private highlightedDevId: string | null = null

  // Feature skill data (set during build)
  private skillMap = new Map<string, EngineFeatureSkill>()
  // Developer → feature titles lookup
  private devFeatures = new Map<string, string[]>()

  // Status color overlay: stores original materials for restoration
  private statusOverlayActive = false
  private statusOriginals = new Map<string, pc.Material>()
  private statusMatAcquisitions = new Map<string, number>() // matKey → acquisition count

  // Threat overlay: halo spheres on features near bugged modules
  private threatHalos: pc.Entity[] = []
  private threatOverlayActive = false
  private threatModules = new Set<string>()

  // BUD lifecycle badges
  private budBadges: { entity: pc.Entity; texture: pc.Texture; material: pc.StandardMaterial }[] = []
  private budBadgesVisible = false
  private budMap = new Map<number, EngineBUD>()

  // Camera reference for billboard rotation
  private cameraEntity: pc.Entity | null = null

  constructor(materials: MaterialFactory) {
    this.materials = materials
    this.dimSystem = new GraphDimSystem(materials)
  }

  /** Initialize materials. Call after MaterialFactory is ready. */
  init(): void {
    this.dimSystem.init()
  }

  /** Set camera entity for billboard rotation. */
  setCameraEntity(camera: pc.Entity): void {
    this.cameraEntity = camera
  }

  /**
   * Build overlays from feature skill data.
   * Creates bus factor rings on feature entities.
   */
  build(
    featureSkills: EngineFeatureSkill[],
    nodeEntities: Map<string, pc.Entity>,
    graphRoot: pc.Entity,
  ): void {
    this.destroyOverlays()

    // Build skill lookup maps
    this.skillMap.clear()
    this.devFeatures.clear()
    for (const skill of featureSkills) {
      this.skillMap.set(skill.feature_title, skill)
      for (const devId of skill.developers) {
        const arr = this.devFeatures.get(devId)
        if (arr) arr.push(skill.feature_title)
        else this.devFeatures.set(devId, [skill.feature_title])
      }
    }

    // Create bus factor ring materials (shared)
    const bus1Mat = this.materials.getColor('gn_ring_bus_1', ...BUS_1_COLOR, {
      metalness: 0,
      gloss: 0.3,
      emissive: [BUS_1_COLOR[0] * 0.8, BUS_1_COLOR[1] * 0.8, BUS_1_COLOR[2] * 0.8],
      opacity: 0.35,
    })
    this.matKeys.push('gn_ring_bus_1')

    const bus2Mat = this.materials.getColor('gn_ring_bus_2', ...BUS_2_COLOR, {
      metalness: 0,
      gloss: 0.3,
      emissive: [BUS_2_COLOR[0] * 0.7, BUS_2_COLOR[1] * 0.7, BUS_2_COLOR[2] * 0.7],
      opacity: 0.3,
    })
    this.matKeys.push('gn_ring_bus_2')

    // Create bus factor rings on feature entities
    for (const [entityId, entity] of nodeEntities) {
      const data = getGraphData(entity)
      if (!data || data.type !== 'graph_feature') continue

      const skill = this.skillMap.get(data.title)
      if (!skill || skill.developer_count > 2) continue

      const mat = skill.developer_count === 1 ? bus1Mat : bus2Mat
      const ring = this.createRingEntity(entity, mat, `BFR_${entityId}`)
      graphRoot.addChild(ring)
      ring.enabled = this.busFactorVisible
      this.busRings.set(entityId, ring)
    }

  }

  /** Toggle bus factor ring visibility. */
  setBusFactorVisible(visible: boolean): void {
    this.busFactorVisible = visible
    for (const ring of this.busRings.values()) {
      ring.enabled = visible
    }
  }

  /** Check if bus factor rings are visible. */
  isBusFactorVisible(): boolean {
    return this.busFactorVisible
  }

  /**
   * Highlight all features a developer is skilled in.
   * Dims unrelated nodes and adds green glow rings on matching features.
   */
  highlightDeveloper(
    userId: string,
    nodeEntities: Map<string, pc.Entity>,
    graphRoot: pc.Entity,
  ): void {
    this.clearHighlight()
    this.highlightedDevId = userId

    const featureTitles = this.devFeatures.get(userId)
    if (!featureTitles || featureTitles.length === 0) return

    const titleSet = new Set(featureTitles)

    // Find matching feature entity IDs
    const activeIds = new Set<string>()
    for (const [entityId, entity] of nodeEntities) {
      const data = getGraphData(entity)
      if (!data) continue
      if (data.type === 'graph_feature' && titleSet.has(data.title)) {
        activeIds.add(entityId)
      }
      // Keep parent repos visible
      if (data.type === 'graph_repo') {
        activeIds.add(entityId)
      }
    }

    // Dim unrelated
    this.dimSystem.dimExcept(activeIds, nodeEntities)

    // Add highlight rings on matching features
    // Acquire highlight material — released in clearHighlight() to balance refCount
    const highlightMat = this.materials.getColor('gn_ring_highlight', ...HIGHLIGHT_COLOR, {
      metalness: 0,
      gloss: 0.6,
      emissive: [HIGHLIGHT_COLOR[0] * 0.6, HIGHLIGHT_COLOR[1] * 0.6, HIGHLIGHT_COLOR[2] * 0.6],
      opacity: 0.8,
    })

    for (const [entityId, entity] of nodeEntities) {
      const data = getGraphData(entity)
      if (!data || data.type !== 'graph_feature') continue
      if (!titleSet.has(data.title)) continue

      const ring = this.createRingEntity(entity, highlightMat, `HL_${entityId}`)
      graphRoot.addChild(ring)
      this.highlightRings.push(ring)
    }
  }

  /** Dim all nodes except those in the active set (no highlight rings). */
  dimOnly(activeEntityIds: Set<string>, nodeEntities: Map<string, pc.Entity>): void {
    this.clearHighlight()
    this.dimSystem.dimExcept(activeEntityIds, nodeEntities)
  }

  /** Clear developer highlight and restore all node opacities. */
  clearHighlight(): void {
    this.highlightedDevId = null
    this.dimSystem.restore()
    if (this.highlightRings.length > 0) {
      // Release the highlight material (one release per highlightDeveloper call)
      this.materials.release('gn_ring_highlight')
    }
    for (const ring of this.highlightRings) {
      ring.destroy()
    }
    this.highlightRings = []
  }

  /** Get currently highlighted developer ID. */
  getHighlightedDevId(): string | null {
    return this.highlightedDevId
  }

  // ─── Status Color Overlay ─────────────────────

  /** Recolor all features by status (planned=blue, in_progress=orange, implemented=green). */
  setStatusOverlay(active: boolean, nodeEntities: Map<string, pc.Entity>): void {
    if (active && !this.statusOverlayActive) {
      // Activate: swap feature materials to status colors
      for (const [entityId, entity] of nodeEntities) {
        const data = getGraphData(entity)
        if (!data || data.type !== 'graph_feature') continue
        if (!entity.render?.meshInstances.length) continue

        const color = STATUS_COLORS[data.status]
        if (!color) continue

        const mi = entity.render.meshInstances[0]
        this.statusOriginals.set(entityId, mi.material)

        const matKey = `gn_status_${data.status}`
        const mat = this.materials.getColor(matKey, color[0], color[1], color[2], {
          metalness: 0.1,
          gloss: 0.5,
          emissive: [color[0] * 0.25, color[1] * 0.25, color[2] * 0.25],
        })
        this.statusMatAcquisitions.set(matKey, (this.statusMatAcquisitions.get(matKey) ?? 0) + 1)
        mi.material = mat
      }
      this.statusOverlayActive = true
    } else if (!active && this.statusOverlayActive) {
      // Deactivate: restore original materials and release acquired status materials
      for (const [entityId, original] of this.statusOriginals) {
        const entity = nodeEntities.get(entityId)
        if (entity?.render?.meshInstances.length) {
          entity.render.meshInstances[0].material = original
        }
      }
      for (const [matKey, count] of this.statusMatAcquisitions) {
        for (let i = 0; i < count; i++) this.materials.release(matKey)
      }
      this.statusOriginals.clear()
      this.statusMatAcquisitions.clear()
      this.statusOverlayActive = false
    }
  }

  isStatusOverlayActive(): boolean {
    return this.statusOverlayActive
  }

  // ─── Threat/Bug Overlay ──────────────────────

  /** Store threat modules for overlay. Call during setData. */
  setThreats(threats: EngineThreat[]): void {
    this.threatModules.clear()
    for (const t of threats) {
      if (t.module) this.threatModules.add(t.module.toLowerCase())
      if (t.branch_name) this.threatModules.add(t.branch_name.toLowerCase())
    }
  }

  /** Toggle threat halos on features near bugged modules. */
  setThreatOverlay(
    active: boolean,
    nodeEntities: Map<string, pc.Entity>,
    graphRoot: pc.Entity,
  ): void {
    if (active && !this.threatOverlayActive) {
      const matKey = 'gn_threat_halo'
      if (!this.matKeys.includes(matKey)) this.matKeys.push(matKey)
      const mat = this.materials.getColor(matKey, ...THREAT_HALO_COLOR, {
        metalness: 0,
        gloss: 0.3,
        emissive: [0.9, 0.05, 0.05],
        opacity: 0.4,
      })

      for (const [, entity] of nodeEntities) {
        const data = getGraphData(entity)
        if (!data || data.type !== 'graph_feature') continue

        const branch = data.branchName?.toLowerCase() ?? ''
        const title = data.title.toLowerCase()
        const matched = [...this.threatModules].some(m => {
          if (m.length < 4) return false // skip short module names to avoid false positives
          return (branch && branch.includes(m)) || title.includes(m)
        })
        if (!matched) continue

        const halo = new pc.Entity('TH_' + entity.name)
        halo.addComponent('render', { type: 'sphere' })
        halo.render!.meshInstances[0].material = mat
        const pos = entity.getPosition()
        halo.setPosition(pos.x, pos.y, pos.z)
        halo.setLocalScale(HALO_SCALE * 1.1, HALO_SCALE * 1.1, HALO_SCALE * 1.1)
        graphRoot.addChild(halo)
        this.threatHalos.push(halo)
      }
      this.threatOverlayActive = true
    } else if (!active && this.threatOverlayActive) {
      for (const h of this.threatHalos) h.destroy()
      this.threatHalos = []
      this.threatOverlayActive = false
    }
  }

  isThreatOverlayActive(): boolean {
    return this.threatOverlayActive
  }

  // ─── BUD Lifecycle Badges ────────────────────

  /** Store BUD data for badge lookup. Call during setData. */
  setBuds(buds: EngineBUD[]): void {
    this.budMap.clear()
    for (const b of buds) this.budMap.set(b.bud_number, b)
  }

  /** Build BUD lifecycle badges on features that have from_bud. */
  buildBudBadges(
    app: pc.AppBase,
    nodeEntities: Map<string, pc.Entity>,
    graphRoot: pc.Entity,
  ): void {
    this.destroyBudBadges()

    for (const [, entity] of nodeEntities) {
      const data = getGraphData(entity)
      if (!data || data.type !== 'graph_feature' || !data.fromBud) continue

      const bud = this.budMap.get(data.fromBud)
      if (!bud) continue

      const label = BUD_STAGE_LABEL[bud.status] ?? bud.status.toUpperCase()
      const color = BUD_STAGE_COLOR[bud.status] ?? '#9E9E9E'
      const badge = this.createBadgeEntity(app, label, color, entity)
      graphRoot.addChild(badge.entity)
      badge.entity.enabled = this.budBadgesVisible
      this.budBadges.push(badge)
    }
  }

  /** Toggle BUD badge visibility. */
  setBudBadgesVisible(visible: boolean): void {
    this.budBadgesVisible = visible
    for (const b of this.budBadges) b.entity.enabled = visible
  }

  isBudBadgesVisible(): boolean {
    return this.budBadgesVisible
  }

  private createBadgeEntity(
    app: pc.AppBase,
    label: string,
    color: string,
    featureEntity: pc.Entity,
  ): { entity: pc.Entity; texture: pc.Texture; material: pc.StandardMaterial } {
    // Render badge text to a canvas
    const canvas = document.createElement('canvas')
    canvas.width = BADGE_CANVAS_W
    canvas.height = BADGE_CANVAS_H
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // Background pill
    const pad = 8
    ctx.fillStyle = color
    ctx.beginPath()
    ctx.roundRect(pad, pad, canvas.width - pad * 2, canvas.height - pad * 2, 10)
    ctx.fill()

    // Text
    ctx.font = `bold ${BADGE_FONT_SIZE}px -apple-system, BlinkMacSystemFont, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#FFFFFF'
    ctx.fillText(label, canvas.width / 2, canvas.height / 2)

    // Upload as texture
    const texture = new pc.Texture(app.graphicsDevice, {
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

    // Material
    // NOTE: MaterialFactory.getColor() doesn't support emissive/opacity texture maps.
    // This material is manually created and destroyed in destroyBudBadges().
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
    const entity = new pc.Entity(`Badge_${label}_${featureEntity.name}`)
    entity.addComponent('render', { type: 'plane' })
    entity.render!.meshInstances[0].material = mat

    const aspect = BADGE_CANVAS_W / BADGE_CANVAS_H
    entity.setLocalScale(BADGE_SCALE * aspect, BADGE_SCALE, 1)

    // Position below feature
    const pos = featureEntity.getPosition()
    entity.setPosition(pos.x, pos.y + BADGE_Y_OFFSET, pos.z)

    return { entity, texture, material: mat }
  }

  private destroyBudBadges(): void {
    for (const b of this.budBadges) {
      b.entity.destroy()
      b.material.destroy()
      b.texture.destroy()
    }
    this.budBadges = []
  }

  /** Update ring positions to follow their parent features (during simulation). */
  updatePositions(nodeEntities: Map<string, pc.Entity>): void {
    for (const [entityId, ring] of this.busRings) {
      const parent = nodeEntities.get(entityId)
      if (parent) {
        const pos = parent.getPosition()
        ring.setPosition(pos.x, pos.y + HALO_Y_OFFSET, pos.z)
      }
    }
    // Highlight rings are static — by the time the user clicks a developer
    // in the panel, the force simulation has settled so positions don't change.

    // Billboard-rotate BUD badges to face camera
    if (this.cameraEntity && this.budBadgesVisible) {
      const camPos = this.cameraEntity.getPosition()
      for (const b of this.budBadges) {
        if (!b.entity.enabled) continue
        b.entity.lookAt(camPos)
        b.entity.rotateLocal(90, 180, 0)
      }
    }
  }

  /** Destroy all overlay entities and release materials. */
  destroy(): void {
    this.destroyOverlays()
    this.dimSystem.destroy()
    for (const key of this.matKeys) {
      this.materials.release(key)
    }
    this.matKeys = []
  }

  // ─── Private ───────────────────────────────────

  private createRingEntity(
    featureEntity: pc.Entity,
    material: pc.StandardMaterial,
    name: string,
  ): pc.Entity {
    const ring = new pc.Entity(name)
    ring.addComponent('render', { type: 'sphere' })
    ring.render!.meshInstances[0].material = material

    // Position at feature location — slightly larger transparent sphere as halo
    const pos = featureEntity.getPosition()
    ring.setPosition(pos.x, pos.y + HALO_Y_OFFSET, pos.z)
    ring.setLocalScale(HALO_SCALE, HALO_SCALE, HALO_SCALE)

    return ring
  }

  private destroyOverlays(): void {
    for (const ring of this.busRings.values()) {
      ring.destroy()
    }
    this.busRings.clear()
    for (const ring of this.highlightRings) {
      ring.destroy()
    }
    this.highlightRings = []
    this.destroyBudBadges()
    for (const h of this.threatHalos) h.destroy()
    this.threatHalos = []
    this.skillMap.clear()
    this.devFeatures.clear()
  }
}
