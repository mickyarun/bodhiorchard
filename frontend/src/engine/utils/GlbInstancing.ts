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
 * GlbInstancing — hardware instancing for GLB scatter systems.
 *
 * Scatter systems (grass, rocks, pines) used to spawn one PlayCanvas entity
 * per scatter point with `loader.instance(asset)`. With 450+ grass blades,
 * 30 rocks, 41 pines that's ~520 entities driving ~520 unique-matrix
 * draw calls per frame — the dominant `uniformMatrix4fv` cost in the prod
 * trace (5.66 ms/frame on Hostinger hardware).
 *
 * This helper collapses each (mesh, material) pair into a single
 * hardware-instanced draw call, regardless of how many scatter points share it.
 * Per-instance world matrices live in a GPU vertex buffer; the GPU pulls them
 * from there instead of via per-draw uniform uploads.
 *
 * It builds on `treetest/instancing.ts:createInstancedEntity` (the proven
 * helper used by Tree3DSystem + LeafSystem) and adds the GLB-specific bits:
 * walking a GLB hierarchy to collect every mesh-instance with its local
 * transform, then composing per-scatter-point world matrices.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import { createInstancedEntity } from '../treetest/instancing'

export interface ScatterTransform {
  x:      number
  y:      number
  z:      number
  yawDeg: number   // rotation around Y axis
  scale:  number   // uniform scale
}

export interface GlbScatterGroup {
  asset:      pc.Asset
  transforms: ScatterTransform[]
}

export interface InstancedScatterResult {
  entities: pc.Entity[]
  vbs:      pc.VertexBuffer[]
}

interface CollectedMeshInstance {
  mesh:        pc.Mesh
  material:    pc.Material
  localMatrix: pc.Mat4   // entity transform relative to the GLB root
}

/**
 * Build hardware-instanced render entities for a list of GLB scatter groups.
 *
 * For each group, every mesh-instance in the GLB hierarchy becomes one
 * instanced draw call submitted with `transforms.length` per-instance matrices.
 * A pine GLB with one mesh-instance + 14 perimeter scatter points → 1 draw
 * (vs 14 with the old per-entity approach). A rock GLB with 2 mesh-instances
 * (rock + dirt cap) and 5 scatter points → 2 draws (vs 10 entities × meshes).
 *
 * The caller owns destruction: `entities[i].destroy()` for each, and
 * `vbs[i].destroy()` to free GPU memory. Group all into a parent entity if
 * you want one-call cleanup.
 *
 * Shadow defaults: castShadows / receiveShadows BOTH default to false. GLB
 * scatter (decorative grass, rocks, perimeter pines) does not contribute
 * meaningfully to shadowing in this scene, and disabling shadows sidesteps
 * the shader-variant assertion that PlayCanvas's shadow renderer trips on
 * for instanced meshes that aren't pre-registered with the program library.
 */
export function buildInstancedGlbs(
  device: pc.GraphicsDevice,
  loader: AssetLoader,
  groups: GlbScatterGroup[],
  opts: {
    namePrefix?:     string
    castShadows?:    boolean
    receiveShadows?: boolean
  } = {},
): InstancedScatterResult {
  const result: InstancedScatterResult = { entities: [], vbs: [] }
  const namePrefix = opts.namePrefix ?? 'InstancedGlb'

  for (let g = 0; g < groups.length; g++) {
    const group = groups[g]
    if (group.transforms.length === 0) continue

    const meshInstances = collectMeshInstances(loader, group.asset)
    if (meshInstances.length === 0) continue

    // For each (mesh, material, localMatrix) in the GLB, build one
    // instanced batch sized to the scatter group's transform count.
    for (let mi = 0; mi < meshInstances.length; mi++) {
      const collected = meshInstances[mi]
      const matrices = composeInstanceMatrices(
        group.transforms, collected.localMatrix,
      )
      const aabb = computeAabbFromMeshBounds(
        group.transforms, collected.mesh, collected.localMatrix,
      )
      const { entity, vb } = createInstancedEntity(
        device,
        collected.mesh,
        collected.material,
        matrices,
        group.transforms.length,
        `${namePrefix}_${g}_${mi}`,
        {
          castShadows:    opts.castShadows    ?? false,
          receiveShadows: opts.receiveShadows ?? false,
          aabb,
        },
      )
      result.entities.push(entity)
      result.vbs.push(vb)
    }
  }

  return result
}

/**
 * AABB tight to the actual instance footprints, including per-instance scale
 * applied to the source mesh's bounds. Critical for tall scatter (pines at
 * scale 7× ≈ 30u tall): a translation-only AABB gives halfY ≈ margin and
 * the frustum culler pops the entire batch when the camera looks at the
 * upper part of the mesh.
 *
 * For each instance: extent[i] = max(transform.scale) * meshHalfExtent.
 * Inflate the translation-AABB by max(extent[i]) on all axes.
 */
function computeAabbFromMeshBounds(
  transforms: ScatterTransform[],
  mesh:       pc.Mesh,
  localMatrix: pc.Mat4,
): pc.BoundingBox {
  const aabb = new pc.BoundingBox()
  if (transforms.length === 0) return aabb

  const meshAabb = mesh.aabb
  const meshHE = meshAabb.halfExtents
  // Account for the local transform's scale baked into mesh-instance positions
  // inside the GLB (e.g. a child entity at offset 0,5,0 would shift mesh top up).
  const localOffset = localMatrix.getTranslation()
  // Largest source-mesh extent before per-instance scale.
  const meshExtent = Math.max(meshHE.x, meshHE.y, meshHE.z)
                     + Math.max(Math.abs(localOffset.x),
                                Math.abs(localOffset.y),
                                Math.abs(localOffset.z))

  let minX = Infinity,  minY = Infinity,  minZ = Infinity
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity
  let maxScale = 0
  for (let i = 0; i < transforms.length; i++) {
    const t = transforms[i]
    if (t.x < minX) minX = t.x
    if (t.x > maxX) maxX = t.x
    if (t.y < minY) minY = t.y
    if (t.y > maxY) maxY = t.y
    if (t.z < minZ) minZ = t.z
    if (t.z > maxZ) maxZ = t.z
    if (t.scale > maxScale) maxScale = t.scale
  }
  const inflate = meshExtent * maxScale
  aabb.center.set((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
  aabb.halfExtents.set(
    (maxX - minX) / 2 + inflate,
    (maxY - minY) / 2 + inflate,
    (maxZ - minZ) / 2 + inflate,
  )
  return aabb
}

/**
 * Walk one freshly-instantiated GLB hierarchy and collect every mesh-instance
 * along with the entity's transform relative to the GLB root. The temporary
 * instance is destroyed after extraction — we only need refs to the shared
 * `pc.Mesh` / `pc.Material` resources, which live on the loaded container.
 *
 * `pc.Mesh` and `pc.Material` are designed to be shared across MeshInstances,
 * so reusing them in our instanced batches is safe — the original asset
 * cache continues to own them. CALLERS MUST NOT MUTATE THE MATERIAL on a
 * batch returned by `buildInstancedGlbs` — every batch sharing this asset
 * would inherit the change because PlayCanvas's container resource hands
 * out the same `pc.StandardMaterial` instance to every clone.
 */
function collectMeshInstances(
  loader: AssetLoader, asset: pc.Asset,
): CollectedMeshInstance[] {
  // The sample entity is detached (no parent) — `instantiateRenderEntity`
  // returns a fresh, unparented hierarchy. So `getWorldTransform()` here
  // equals the entity's local transform with no parent influence.
  const sample = loader.instance(asset)
  const out: CollectedMeshInstance[] = []
  // GLB roots normally have identity transform when freshly instanced, but
  // some kenney rigged assets bake scale/offset into the root. The
  // root-inverse cancels any such bake so each child's local matrix is
  // expressed relative to the GLB origin, not the baked root.
  const rootInverse = sample.getWorldTransform().clone().invert()
  walkRender(sample, rootInverse, out)
  sample.destroy()
  return out
}

function walkRender(
  entity: pc.Entity, rootInverse: pc.Mat4, out: CollectedMeshInstance[],
): void {
  const render = entity.render
  if (render && render.meshInstances) {
    const local = new pc.Mat4().mul2(rootInverse, entity.getWorldTransform())
    for (const mi of render.meshInstances) {
      out.push({
        mesh:        mi.mesh,
        material:    mi.material,
        localMatrix: local.clone(),
      })
    }
  }
  for (const child of entity.children) {
    if (child instanceof pc.Entity) walkRender(child, rootInverse, out)
  }
}

/**
 * Build a packed Float32Array of `count` mat4 instance matrices from a list
 * of scatter transforms and one local matrix (the mesh-instance's offset
 * inside its GLB hierarchy). Output layout matches PlayCanvas's default
 * instancing format: 16 floats per instance, column-major.
 *
 * Per-instance matrix = T(x,y,z) * Ry(yaw) * S(scale) * localMatrix
 *
 * Uses scratch Mat4 instances to avoid allocations in the inner loop —
 * scatter systems can run hundreds of these per build.
 */
const _scratchScatter = new pc.Mat4()
const _scratchLocal   = new pc.Mat4()
const _scratchPos     = new pc.Vec3()
const _scratchRot     = new pc.Quat()
const _scratchScale   = new pc.Vec3()

function composeInstanceMatrices(
  transforms: ScatterTransform[],
  localMatrix: pc.Mat4,
): Float32Array {
  const count = transforms.length
  const out = new Float32Array(count * 16)
  for (let i = 0; i < count; i++) {
    const t = transforms[i]
    _scratchPos.set(t.x, t.y, t.z)
    _scratchRot.setFromEulerAngles(0, t.yawDeg, 0)
    _scratchScale.set(t.scale, t.scale, t.scale)
    _scratchScatter.setTRS(_scratchPos, _scratchRot, _scratchScale)
    _scratchLocal.mul2(_scratchScatter, localMatrix)
    out.set(_scratchLocal.data, i * 16)
  }
  return out
}
