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
 * ArcBuilder — shared quadratic Bezier arc computation and box-segment construction.
 *
 * Used by GraphEdgeBuilder (repo-feature arcs) and GraphCrossRepoSystem (cross-repo arcs).
 * Avoids duplicating the arc math in two places.
 */
import * as pc from 'playcanvas'

const DEFAULT_SEGMENTS = 8

export class ArcBuilder {
  private readonly segments: number
  private readonly _arcPoints: pc.Vec3[]
  private readonly _scratchMid = new pc.Vec3()

  constructor(segments = DEFAULT_SEGMENTS) {
    this.segments = segments
    this._arcPoints = Array.from({ length: segments + 1 }, () => new pc.Vec3())
  }

  /** Compute quadratic Bezier arc points into pre-allocated array. */
  computeArcPoints(from: pc.Vec3, to: pc.Vec3, arcHeight: number): readonly pc.Vec3[] {
    const midX = (from.x + to.x) / 2
    const midY = (from.y + to.y) / 2 + arcHeight
    const midZ = (from.z + to.z) / 2

    for (let i = 0; i <= this.segments; i++) {
      const t = i / this.segments
      const invT = 1 - t
      this._arcPoints[i].set(
        invT * invT * from.x + 2 * invT * t * midX + t * t * to.x,
        invT * invT * from.y + 2 * invT * t * midY + t * t * to.y,
        invT * invT * from.z + 2 * invT * t * midZ + t * t * to.z,
      )
    }
    return this._arcPoints
  }

  /** Create box-segment entities along an arc. Returns the segment entities. */
  buildSegments(
    from: pc.Vec3,
    to: pc.Vec3,
    arcHeight: number,
    thickness: number,
    material: pc.StandardMaterial,
    parent: pc.Entity,
    namePrefix: string,
  ): pc.Entity[] {
    const points = this.computeArcPoints(from, to, arcHeight)
    const segments: pc.Entity[] = []

    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i]
      const b = points[i + 1]
      this._scratchMid.set((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2)
      const len = a.distance(b)

      const seg = new pc.Entity(`${namePrefix}_${i}`)
      seg.addComponent('render', { type: 'box' })
      seg.setPosition(this._scratchMid.x, this._scratchMid.y, this._scratchMid.z)
      seg.setLocalScale(thickness, thickness, len)
      seg.lookAt(b)

      seg.render!.meshInstances[0].material = material
      parent.addChild(seg)
      segments.push(seg)
    }

    return segments
  }

  /** Update existing segments to match new arc positions. */
  updateSegments(
    segments: pc.Entity[],
    from: pc.Vec3,
    to: pc.Vec3,
    arcHeight: number,
    thickness: number,
  ): void {
    const points = this.computeArcPoints(from, to, arcHeight)

    for (let i = 0; i < segments.length && i < points.length - 1; i++) {
      const a = points[i]
      const b = points[i + 1]
      const seg = segments[i]

      seg.setPosition((a.x + b.x) / 2, (a.y + b.y) / 2, (a.z + b.z) / 2)
      seg.setLocalScale(thickness, thickness, a.distance(b))
      seg.lookAt(b)
    }
  }
}
