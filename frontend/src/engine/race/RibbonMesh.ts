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
 * RibbonMesh — procedural closed-ribbon geometry following the loop path.
 *
 * Replaces AnnulusMesh for the organic circuit: one ribbon per painted
 * surface (the sand road, each lane divider), built as a closed triangle
 * strip between two lateral offsets of the LoopPath centreline. Vertices
 * are loopPose samples in WORLD coordinates (the loop is anchored at the
 * world origin), so the owning entity stays at the origin — unlike the
 * old annulus, which was centred on the circle's centre.
 *
 * Ownership: the returned pc.Mesh holds GPU vertex/index buffers that
 * `entity.destroy()` does NOT free — callers must release it via
 * `safeDestroyMesh` (see dispose.ts) on teardown.
 */
import * as pc from 'playcanvas'
import { loopPose } from '@shared/race/LoopPath'

export interface RibbonMeshOptions {
  /** Lap length — selects the cached LoopPath table. */
  circumferenceM: number
  /**
   * The ribbon's two lateral edges (metres from the centreline; positive
   * = toward the inside of the loop, as in loopPose). Order-insensitive.
   */
  lateralAM: number
  lateralBM: number
  /** Arc slices around the loop — chord error shrinks as this grows. */
  segments: number
  /** Local Y of the ribbon plane (paint layers float above the sand). */
  y: number
}

/**
 * Build a flat closed ribbon mesh lying in the XZ plane, normals +Y.
 *
 * Winding mirrors the proven annulus pattern: per arc column the vertex
 * pair is (inner = more-inward lateral, outer), and each quad is emitted
 * as (inner, outerNext, outer) + (inner, innerNext, outerNext). The loop
 * traversal direction (heading from +X toward +Z) matches the annulus's
 * CCW θ, so the ribbon is visible from above with default back-face
 * culling, exactly like the rings it replaces.
 */
export function buildRibbonMesh(device: pc.GraphicsDevice, opts: RibbonMeshOptions): pc.Mesh {
  const { circumferenceM, segments, y } = opts
  if (!(circumferenceM > 0)) {
    throw new Error(`buildRibbonMesh: circumferenceM=${circumferenceM} must be > 0`)
  }
  if (segments < 3) {
    throw new Error(`buildRibbonMesh: segments=${segments} must be >= 3`)
  }
  if (opts.lateralAM === opts.lateralBM) {
    throw new Error(`buildRibbonMesh: degenerate ribbon (both edges at ${opts.lateralAM})`)
  }
  const innerLateralM = Math.max(opts.lateralAM, opts.lateralBM)
  const outerLateralM = Math.min(opts.lateralAM, opts.lateralBM)

  const positions: number[] = []
  const normals: number[] = []
  const uvs: number[] = []
  const indices: number[] = []

  // segments + 1 vertex columns so the seam shares positions exactly —
  // loopPose(0) === loopPose(circumference) by the table's closure.
  for (let i = 0; i <= segments; i++) {
    const arcM = (i / segments) * circumferenceM
    const inner = loopPose(arcM, circumferenceM, innerLateralM)
    const outer = loopPose(arcM, circumferenceM, outerLateralM)
    positions.push(inner.x, y, inner.z)
    positions.push(outer.x, y, outer.z)
    normals.push(0, 1, 0, 0, 1, 0)
    // u runs around the loop, v inner→outer — only matters if a texture
    // is ever dropped onto a ribbon (the race palette is solid colour).
    uvs.push(i / segments, 0, i / segments, 1)
  }

  for (let i = 0; i < segments; i++) {
    const inner = i * 2
    const outer = inner + 1
    const innerNext = inner + 2
    const outerNext = inner + 3
    indices.push(inner, outerNext, outer)
    indices.push(inner, innerNext, outerNext)
  }

  return pc.createMesh(device, positions, { normals, uvs, indices })
}
