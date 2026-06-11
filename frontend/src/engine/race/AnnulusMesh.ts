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
 * AnnulusMesh — procedural flat ring geometry for the circuit track.
 *
 * One annulus per painted surface (sand ring, each lane-divider ring):
 * a triangle strip of `segments` quads between an inner and outer radius,
 * lying in the local XZ plane with all normals +Y. The mesh is centred on
 * the local origin — callers position the owning entity at the circle's
 * world centre.
 *
 * Ownership: the returned pc.Mesh holds GPU vertex/index buffers that
 * `entity.destroy()` does NOT free — callers must release it via
 * `safeDestroyMesh` (see dispose.ts) on teardown.
 */
import * as pc from 'playcanvas'

/**
 * Build a flat ring mesh.
 *
 * Winding: PlayCanvas front faces are counter-clockwise. Each quad is
 * emitted as (inner_i, outer_i+1, outer_i) + (inner_i, inner_i+1,
 * outer_i+1), which winds CCW when viewed from +Y — so the ring is
 * visible from above with default back-face culling.
 *
 * @param device   Graphics device the buffers are created on.
 * @param innerRadiusM Inner edge radius (metres).
 * @param outerRadiusM Outer edge radius (metres).
 * @param segments Number of radial slices — chord error shrinks as this grows.
 * @param y        Local Y of the ring plane (paint layers float above sand).
 */
export function buildAnnulusMesh(
  device: pc.GraphicsDevice,
  innerRadiusM: number,
  outerRadiusM: number,
  segments: number,
  y: number,
): pc.Mesh {
  if (!(outerRadiusM > innerRadiusM) || innerRadiusM < 0) {
    throw new Error(
      `buildAnnulusMesh: invalid radii inner=${innerRadiusM} outer=${outerRadiusM}`,
    )
  }
  if (segments < 3) {
    throw new Error(`buildAnnulusMesh: segments=${segments} must be >= 3`)
  }

  const positions: number[] = []
  const normals: number[] = []
  const uvs: number[] = []
  const indices: number[] = []

  // segments + 1 vertex columns so the seam shares positions exactly.
  for (let i = 0; i <= segments; i++) {
    const theta = (i / segments) * Math.PI * 2
    const cos = Math.cos(theta)
    const sin = Math.sin(theta)
    positions.push(innerRadiusM * cos, y, innerRadiusM * sin)
    positions.push(outerRadiusM * cos, y, outerRadiusM * sin)
    normals.push(0, 1, 0, 0, 1, 0)
    // Radial UV mapping: u runs around the ring, v inner→outer. The race
    // palette is solid colour so this only matters if a texture is ever
    // dropped onto a ring later.
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
