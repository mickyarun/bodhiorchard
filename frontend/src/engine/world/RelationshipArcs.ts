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
 * RelationshipArcs — Bezier curve arcs between trees.
 *
 * Renders colored arcs as hardware-instanced box segments: ONE draw call
 * per rel_type (CALLS=blue, IMPORTS=green, EXTENDS=orange, IMPLEMENTS=purple)
 * instead of 16 entities per arc. Each arc keeps a render-less parent
 * entity at the curve apex carrying the 'pickable' tag + relationship
 * data, so hover/click tooltips keep working. Togglable visibility —
 * arcs build disabled and cost nothing until toggled on.
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { EngineRelationship, RelType } from '../types'
import { setTreeData } from './TreeNodeData'
import { createInstancedEntity, computeInstanceAabb } from '../treetest/instancing'

const ARC_SEGMENTS = 16
const SEGMENT_THICKNESS = 0.06
// When multiple arcs share the same (source_repo, target_repo), fan them
// vertically so each feature has a visibly distinct curve. The first arc
// sits at FAN_BASE_HEIGHT; each subsequent arc adds FAN_STEP. After
// FAN_LINEAR_LIMIT arcs the step compresses to FAN_TAIL_STEP so a heavily
// connected repo pair (20+ features) doesn't shoot arcs past the canopy.
const FAN_BASE_HEIGHT = 4
const FAN_STEP = 3
const FAN_LINEAR_LIMIT = 8
const FAN_TAIL_STEP = 0.5

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
  private vbs: pc.VertexBuffer[] = []
  private boxMesh: pc.Mesh | null = null

  build(
    materials: MaterialFactory,
    relationships: EngineRelationship[],
    treePositions: Map<string, pc.Vec3>,
    device: pc.GraphicsDevice,
  ): pc.Entity {
    this.root = new pc.Entity('RelationshipArcs')
    this.root.enabled = this.visible

    // Group arcs by unordered repo pair so the per-pair index can spread
    // overlapping arcs vertically (one feature → one curve at a unique
    // height). Sorting the pair makes A↔B and B↔A share the same bucket.
    const pairIndex = new Map<string, number>()
    // Segment world matrices accumulate per rel_type → one instanced
    // batch per type at the end.
    const segmentsByType = new Map<RelType, number[]>()

    for (const rel of relationships) {
      const srcPos = treePositions.get(rel.source_repo)
      const tgtPos = treePositions.get(rel.target_repo)
      if (!srcPos || !tgtPos) continue
      if (rel.source_repo === rel.target_repo) continue

      const pairKey =
        rel.source_repo < rel.target_repo
          ? `${rel.source_repo}::${rel.target_repo}`
          : `${rel.target_repo}::${rel.source_repo}`
      const fanIndex = pairIndex.get(pairKey) ?? 0
      pairIndex.set(pairKey, fanIndex + 1)

      this.appendArc(segmentsByType, srcPos, tgtPos, rel, fanIndex)
    }

    // One instanced draw per rel_type that actually has arcs.
    for (const [relType, flat] of segmentsByType) {
      const count = flat.length / 16
      if (count === 0) continue
      const color = REL_COLORS[relType]
      const matKey = `arc_${relType}`
      this.materialKeys.add(matKey)
      const mat = materials.getColor(matKey, color[0], color[1], color[2], {
        emissive: [color[0] * 0.5, color[1] * 0.5, color[2] * 0.5],
        opacity: 0.7,
      })
      const matrices = new Float32Array(flat)
      const aabb = computeInstanceAabb(matrices, count, 2)
      const { entity, vb } = createInstancedEntity(
        device, this.getBoxMesh(device), mat, matrices, count,
        `ArcSegments_${relType}`, { aabb },
      )
      this.root.addChild(entity)
      this.vbs.push(vb)
    }

    return this.root
  }

  /**
   * Compute one arc's bezier segments into the per-type matrix bucket and
   * create its render-less pick parent at the curve apex (the old per-arc
   * parent sat at the origin, making the 3D ray-sphere pick test
   * effectively dead — the apex anchor makes arcs sensibly hoverable).
   */
  private appendArc(
    segmentsByType: Map<RelType, number[]>,
    from: pc.Vec3,
    to: pc.Vec3,
    rel: EngineRelationship,
    fanIndex: number,
  ): void {
    // Per-feature arcs always have weight=1, so heights are driven by
    // the per-pair fan index — a single arc sits at FAN_BASE_HEIGHT, and
    // additional arcs stack uniformly above it. After FAN_LINEAR_LIMIT
    // the step compresses to keep the topmost arc within the canopy band.
    // ``weight`` is retained on ``EngineRelationship`` for future use.
    const linearArcs = Math.min(fanIndex, FAN_LINEAR_LIMIT)
    const tailArcs = Math.max(0, fanIndex - FAN_LINEAR_LIMIT)
    const midY = FAN_BASE_HEIGHT + linearArcs * FAN_STEP + tailArcs * FAN_TAIL_STEP
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

    // Render-less pick anchor at the curve apex
    const arcParent = new pc.Entity(`Arc_${rel.rel_type}_${rel.source_repo}_${rel.target_repo}`)
    arcParent.tags.add('pickable')
    const apex = points[Math.floor(points.length / 2)]
    arcParent.setPosition(apex.x, apex.y, apex.z)
    setTreeData(arcParent, {
      type: 'tree_relationship',
      sourceRepo: rel.source_repo,
      targetRepo: rel.target_repo,
      relType: rel.rel_type,
      weight: rel.weight,
      featureTitle: rel.feature_title ?? null,
    })
    this.root!.addChild(arcParent)

    // Segment matrices: unit box scaled to (thickness, thickness, len),
    // -Z forward aligned along the segment (same as entity.lookAt).
    let bucket = segmentsByType.get(rel.rel_type)
    if (!bucket) {
      bucket = []
      segmentsByType.set(rel.rel_type, bucket)
    }
    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i]
      const b = points[i + 1]
      _segMid.set((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2)
      const len = a.distance(b)
      _segMat.setLookAt(_segMid, b, pc.Vec3.UP)
      _segScale.setScale(SEGMENT_THICKNESS, SEGMENT_THICKNESS, len)
      _segMat.mul(_segScale)
      for (let k = 0; k < 16; k++) bucket.push(_segMat.data[k])
    }
  }

  private getBoxMesh(device: pc.GraphicsDevice): pc.Mesh {
    if (!this.boxMesh) {
      this.boxMesh = pc.Mesh.fromGeometry(device, new pc.BoxGeometry())
    }
    return this.boxMesh
  }

  get isVisible(): boolean { return this.visible }

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

    for (const vb of this.vbs) vb.destroy()
    this.vbs = []
    if (this.boxMesh) {
      this.boxMesh.vertexBuffer?.destroy()
      this.boxMesh.indexBuffer?.[0]?.destroy()
      this.boxMesh = null
    }
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}

// Scratch objects for the segment-matrix loop — zero per-segment allocation.
const _segMid = new pc.Vec3()
const _segMat = new pc.Mat4()
const _segScale = new pc.Mat4()
