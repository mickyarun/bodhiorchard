/**
 * RelationshipArcs — Bezier curve arcs between trees.
 *
 * Renders colored arcs using small box segments between source and target trees.
 * Color by rel_type: CALLS=blue, IMPORTS=green, EXTENDS=orange, IMPLEMENTS=purple.
 * Togglable visibility.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { EngineRelationship, RelType } from '../types'
import { setTreeData } from './TreeNodeData'

const ARC_HEIGHT = 8
const ARC_SEGMENTS = 16
const SEGMENT_THICKNESS = 0.06

const REL_COLORS: Record<RelType, [number, number, number]> = {
  CALLS:      [0.3, 0.5, 0.9],
  IMPORTS:    [0.3, 0.8, 0.4],
  EXTENDS:    [0.9, 0.6, 0.2],
  IMPLEMENTS: [0.7, 0.3, 0.8],
}

export class RelationshipArcs {
  private root: pc.Entity | null = null
  private visible = false
  private materialKeys = new Set<string>()

  build(
    materials: MaterialFactory,
    relationships: EngineRelationship[],
    treePositions: Map<string, pc.Vec3>,
  ): pc.Entity {
    this.root = new pc.Entity('RelationshipArcs')
    this.root.enabled = this.visible

    for (const rel of relationships) {
      const srcPos = treePositions.get(rel.source_repo)
      const tgtPos = treePositions.get(rel.target_repo)
      if (!srcPos || !tgtPos) continue
      if (rel.source_repo === rel.target_repo) continue

      this.createArc(materials, srcPos, tgtPos, rel)
    }

    return this.root
  }

  private createArc(
    materials: MaterialFactory,
    from: pc.Vec3,
    to: pc.Vec3,
    rel: EngineRelationship,
  ): void {
    const color = REL_COLORS[rel.rel_type]
    const matKey = `arc_${rel.rel_type}`
    this.materialKeys.add(matKey)
    const mat = materials.getColor(matKey, color[0], color[1], color[2], {
      emissive: [color[0] * 0.5, color[1] * 0.5, color[2] * 0.5],
      opacity: 0.7,
    })

    const midY = ARC_HEIGHT * Math.min(rel.weight / 5, 2)
    const midX = (from.x + to.x) / 2
    const midZ = (from.z + to.z) / 2

    // Generate bezier curve points
    const points: pc.Vec3[] = []
    for (let i = 0; i <= ARC_SEGMENTS; i++) {
      const t = i / ARC_SEGMENTS
      const invT = 1 - t
      const x = invT * invT * from.x + 2 * invT * t * midX + t * t * to.x
      const y = invT * invT * from.y + 2 * invT * t * (from.y + midY) + t * t * to.y
      const z = invT * invT * from.z + 2 * invT * t * midZ + t * t * to.z
      points.push(new pc.Vec3(x, y + 3, z))
    }

    // Create small box segments between consecutive points
    const arcParent = new pc.Entity(`Arc_${rel.rel_type}_${rel.source_repo}_${rel.target_repo}`)
    arcParent.tags.add('pickable')
    setTreeData(arcParent, {
      type: 'tree_relationship',
      sourceRepo: rel.source_repo,
      targetRepo: rel.target_repo,
      relType: rel.rel_type,
      weight: rel.weight,
    })

    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i]
      const b = points[i + 1]
      const mid = new pc.Vec3(
        (a.x + b.x) / 2,
        (a.y + b.y) / 2,
        (a.z + b.z) / 2,
      )
      const len = a.distance(b)

      const seg = new pc.Entity(`Seg_${i}`)
      seg.addComponent('render', { type: 'box' })
      seg.setPosition(mid.x, mid.y, mid.z)
      seg.setLocalScale(SEGMENT_THICKNESS, SEGMENT_THICKNESS, len)
      seg.lookAt(b)

      seg.render!.meshInstances[0].material = mat
      arcParent.addChild(seg)
    }

    this.root!.addChild(arcParent)
  }

  toggle(): boolean {
    this.visible = !this.visible
    if (this.root) this.root.enabled = this.visible
    return this.visible
  }

  setVisible(visible: boolean): void {
    this.visible = visible
    if (this.root) this.root.enabled = this.visible
  }

  destroy(materials?: MaterialFactory): void {
    // Release acquired materials
    if (materials) {
      for (const key of this.materialKeys) {
        materials.release(key)
      }
    }
    this.materialKeys.clear()

    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
