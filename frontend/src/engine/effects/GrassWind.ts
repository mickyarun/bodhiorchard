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
 * GrassWind — vertex wind sway for the instanced grass/flower scatter.
 *
 * Overrides the `transformVS` shader chunk on the scatter's CLONED
 * materials (never the shared GLB container materials): world position is
 * displaced by a two-frequency sine after the model matrix is applied, so
 * it composes with hardware instancing (the instanced `getModelMatrix`
 * variant is a separate chunk that this one calls unchanged).
 *
 * Height weighting uses mesh-local Y squared — blade roots stay anchored,
 * tips sway. Phase derives from world XZ so neighbouring tufts move in a
 * traveling wave rather than in lockstep.
 *
 * Per-frame cost: one float uniform per registered material.
 */
import * as pc from 'playcanvas'

/** Default transform chunk (PlayCanvas 2.18) with wind displacement added
 *  after world-position evaluation. Kept structurally identical otherwise —
 *  getModelMatrix() still comes from the (instancing) transform core. */
const WIND_TRANSFORM_VS = /* glsl */ `
uniform float uWindTime;
uniform float uWindStrength;

vec4 evalWorldPosition(vec3 vertexPosition, mat4 modelMatrix) {
    vec3 localPos = getLocalPosition(vertexPosition);
    vec4 posW = modelMatrix * vec4(localPos, 1.0);

    // Wind sway — height-squared weighting anchors the blade roots.
    float windH = max(localPos.y, 0.0);
    float phase = posW.x * 0.35 + posW.z * 0.28;
    float sway = (sin(uWindTime * 1.6 + phase) + 0.4 * sin(uWindTime * 3.7 + phase * 1.7))
               * uWindStrength * windH * windH;
    posW.x += sway;
    posW.z += sway * 0.6;

    return posW;
}

vec4 getPosition() {
    dModelMatrix = getModelMatrix();
    vec4 posW = evalWorldPosition(vertex_position.xyz, dModelMatrix);
    dPositionW = posW.xyz;
    return matrix_viewProjection * posW;
}

vec3 getWorldPosition() {
    return dPositionW;
}
`

export class GrassWind {
  private materials: pc.Material[] = []
  private time = 0

  /**
   * Install the wind chunk on a set of materials. The materials MUST be
   * clones owned by the caller (e.g. GlbInstancing tint clones) — chunk
   * overrides on shared GLB materials would leak into unrelated batches.
   */
  apply(materials: pc.Material[], strength: number): void {
    for (const mat of materials) {
      mat.getShaderChunks(pc.SHADERLANGUAGE_GLSL).set('transformVS', WIND_TRANSFORM_VS)
      mat.shaderChunksVersion = '2.8'
      mat.setParameter('uWindStrength', strength)
      mat.setParameter('uWindTime', 0)
      mat.update()
      this.materials.push(mat)
    }
  }

  /** Advance the shared wind clock. Call once per frame. */
  update(dt: number): void {
    this.time += dt
    for (const mat of this.materials) {
      mat.setParameter('uWindTime', this.time)
    }
  }

  /** Drop material refs (the owner destroys the materials themselves). */
  clear(): void {
    this.materials = []
  }
}
