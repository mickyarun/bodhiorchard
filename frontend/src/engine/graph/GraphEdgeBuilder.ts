/**
 * GraphEdgeBuilder — creates curved arc edges between graph nodes.
 *
 * Uses multi-segment box arcs (Bezier curves) for smooth, rounded connections.
 * Feature→repo edges arc upward slightly; repo→repo edges arc higher.
 * Edge color matches the source repo color (passed in).
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'

const SEGMENTS = 8
const SEGMENT_THICKNESS = 0.04
const FEATURE_ARC_HEIGHT = 0.4
const EDGE_OPACITY = 0.5

const DEFAULT_EDGE_COLOR: [number, number, number] = [0.6, 0.6, 0.7]

export interface EdgeHandle {
  parent: pc.Entity
  segments: pc.Entity[]
  sourceId: string
  targetId: string
}

export class GraphEdgeBuilder {
  private materials: MaterialFactory
  private matKeysUsed = new Set<string>()

  // Pre-allocated arc points to avoid per-frame Vec3 allocations
  private readonly _arcPoints: pc.Vec3[] = Array.from(
    { length: SEGMENTS + 1 },
    () => new pc.Vec3(),
  )

  constructor(materials: MaterialFactory) {
    this.materials = materials
  }

  /** Create a curved arc edge between two positions. */
  buildEdge(
    from: pc.Vec3,
    to: pc.Vec3,
    edgeId: string,
    color?: [number, number, number],
  ): EdgeHandle {
    const parent = new pc.Entity(`GE_${edgeId}`)
    const segments: pc.Entity[] = []

    const c = color ?? DEFAULT_EDGE_COLOR
    const matKey = `gn_edge_${c[0].toFixed(2)}_${c[1].toFixed(2)}_${c[2].toFixed(2)}`
    if (!this.matKeysUsed.has(matKey)) {
      this.matKeysUsed.add(matKey)
    }
    const mat = this.materials.getColor(matKey, c[0], c[1], c[2], {
      metalness: 0,
      gloss: 0.3,
      opacity: EDGE_OPACITY,
      emissive: [c[0] * 0.3, c[1] * 0.3, c[2] * 0.3],
    })

    // Create bezier curve points
    const points = this.computeArcPoints(from, to, FEATURE_ARC_HEIGHT)

    // Create box segments between consecutive points
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
      parent.addChild(seg)
      segments.push(seg)
    }

    return { parent, segments, sourceId: edgeId.split('__')[0], targetId: edgeId.split('__')[1] }
  }

  /** Update an existing edge arc to new positions. */
  updateEdge(handle: EdgeHandle, from: pc.Vec3, to: pc.Vec3): void {
    const points = this.computeArcPoints(from, to, FEATURE_ARC_HEIGHT)

    for (let i = 0; i < handle.segments.length && i < points.length - 1; i++) {
      const a = points[i]
      const b = points[i + 1]
      const seg = handle.segments[i]

      seg.setPosition(
        (a.x + b.x) / 2,
        (a.y + b.y) / 2,
        (a.z + b.z) / 2,
      )
      seg.setLocalScale(SEGMENT_THICKNESS, SEGMENT_THICKNESS, a.distance(b))
      seg.lookAt(b)
    }
  }

  /** Compute quadratic bezier arc points into pre-allocated array. */
  private computeArcPoints(from: pc.Vec3, to: pc.Vec3, arcHeight: number): readonly pc.Vec3[] {
    const midX = (from.x + to.x) / 2
    const midY = (from.y + to.y) / 2 + arcHeight
    const midZ = (from.z + to.z) / 2

    for (let i = 0; i <= SEGMENTS; i++) {
      const t = i / SEGMENTS
      const invT = 1 - t
      this._arcPoints[i].set(
        invT * invT * from.x + 2 * invT * t * midX + t * t * to.x,
        invT * invT * from.y + 2 * invT * t * midY + t * t * to.y,
        invT * invT * from.z + 2 * invT * t * midZ + t * t * to.z,
      )
    }
    return this._arcPoints
  }

  /** Release all materials created by this builder. */
  destroy(): void {
    for (const key of this.matKeysUsed) {
      this.materials.release(key)
    }
    this.matKeysUsed.clear()
  }
}
