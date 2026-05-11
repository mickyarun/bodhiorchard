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
 * GraphEdgeBuilder — creates curved arc edges between graph nodes.
 *
 * Uses ArcBuilder for shared Bezier arc math.
 * Feature→repo edges arc upward slightly; repo→repo edges arc higher.
 * Edge color matches the source repo color (passed in).
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { ArcBuilder } from './ArcBuilder'

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
  private matKeysUsed: string[] = []
  private arc = new ArcBuilder()

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

    const c = color ?? DEFAULT_EDGE_COLOR
    const matKey = `gn_edge_${c[0].toFixed(2)}_${c[1].toFixed(2)}_${c[2].toFixed(2)}`
    this.matKeysUsed.push(matKey)
    const mat = this.materials.getColor(matKey, c[0], c[1], c[2], {
      metalness: 0,
      gloss: 0.3,
      opacity: EDGE_OPACITY,
      emissive: [c[0] * 0.3, c[1] * 0.3, c[2] * 0.3],
    })

    const segments = this.arc.buildSegments(
      from, to, FEATURE_ARC_HEIGHT, SEGMENT_THICKNESS, mat, parent, 'Seg',
    )

    return { parent, segments, sourceId: edgeId.split('__')[0], targetId: edgeId.split('__')[1] }
  }

  /** Update an existing edge arc to new positions. */
  updateEdge(handle: EdgeHandle, from: pc.Vec3, to: pc.Vec3): void {
    this.arc.updateSegments(handle.segments, from, to, FEATURE_ARC_HEIGHT, SEGMENT_THICKNESS)
  }

  /** Release all materials acquired by this builder (one release per acquisition). */
  destroy(): void {
    for (const key of this.matKeysUsed) {
      this.materials.release(key)
    }
    this.matKeysUsed = []
  }
}
