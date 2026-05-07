// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * instancing — shared helper for building a hardware-instanced render entity.
 *
 * Both Tree3DSystem (branches) and LeafSystem (leaves) collapse thousands of
 * per-element entities into a single draw call per material using PlayCanvas's
 * hardware-instancing path. The plumbing — vertex format, instance VertexBuffer,
 * MeshInstance/cull/shadow settings, entity/render-component wiring — is
 * identical in both places; only the mesh, material, and parent differ.
 */
import * as pc from 'playcanvas'

export interface InstancedEntityResult {
  entity: pc.Entity
  vb:     pc.VertexBuffer
}

/**
 * Build a render entity whose single MeshInstance is hardware-instanced across
 * `count` per-instance mat4 world transforms. Returns the entity (caller
 * decides where to parent) and the VertexBuffer (caller must destroy on
 * teardown to free GPU memory).
 *
 * Shadow handling: castShadows / receiveShadows MUST be passed in the render
 * component options because addComponent('render', {meshInstances}) OVERRIDES
 * each MeshInstance's castShadow to the component's value. Both default to
 * false — instanced tree meshes don't cast shadows (big perf win, and also
 * avoids shader-variant assertion loops in the shadow renderer for meshes
 * that aren't pre-registered with the program library).
 *
 * Culling: pass a precomputed `aabb` covering every instance's footprint to
 * enable PlayCanvas's per-MeshInstance frustum culling. Without it the
 * MeshInstance falls back to the source mesh's AABB alone, which cannot
 * represent the swarm of instance positions, so we'd have to disable cull
 * entirely and pay full draw cost for off-screen batches. Use
 * `computeInstanceAabb` (below) to build it from the same matrix array.
 */
export function createInstancedEntity(
  device:    pc.GraphicsDevice,
  mesh:      pc.Mesh,
  material:  pc.Material,
  matrices:  Float32Array,
  count:     number,
  name:      string,
  opts: {
    castShadows?:    boolean
    receiveShadows?: boolean
    aabb?:           pc.BoundingBox
  } = {},
): InstancedEntityResult {
  const format = pc.VertexFormat.getDefaultInstancingFormat(device)
  const vb = new pc.VertexBuffer(device, format, count, {
    // PlayCanvas's TS type narrows `data` to ArrayBuffer, but the runtime
    // reads only `.byteLength` and upstream (glb-container-resource.js) passes
    // the TypedArray directly. Cast through unknown to match actual behavior.
    data: matrices as unknown as ArrayBuffer,
  })

  const mi = new pc.MeshInstance(mesh, material)
  // Hardware-instancing culling lives in two places per PlayCanvas's API:
  //   1. `setInstancing(vb, cull)` — second arg flips the instanced batch's
  //      cull-aware draw path on. Without it, the whole batch is always
  //      submitted regardless of camera frustum.
  //   2. `entity.render.customAabb` (set below) — the AABB that covers every
  //      instance, used by the culler to decide if the batch is visible.
  // Setting `mi.cull = true` directly or `mi.setCustomAabb()` (the @ignore'd
  // internal helper) does NOT replace these — combining them with
  // setInstancing leaves the MeshInstance in an inconsistent state and the
  // forward renderer crashes inside draw() reading undefined fields.
  mi.setInstancing(vb, opts.aabb != null)

  const entity = new pc.Entity(name)
  entity.addComponent('render', {
    meshInstances:  [mi],
    castShadows:    opts.castShadows    ?? false,
    receiveShadows: opts.receiveShadows ?? false,
  })

  if (opts.aabb && entity.render) {
    entity.render.customAabb = opts.aabb
  }

  return { entity, vb }
}

/**
 * Build an AABB enclosing every instance's translation in a packed mat4 array
 * (column-major, 16 floats per instance — translation in cols 12, 13, 14).
 *
 * `margin` inflates each axis to absorb (a) the per-instance mesh extent
 * around its origin (e.g. a unit cylinder rotated and scaled by the instance
 * matrix), and (b) a bit of slack so a swaying parent transform can rotate
 * the AABB in world space without clipping actual instances out of the frustum.
 *
 * Returns a zero-extents box if `count` is 0 — caller should skip culling
 * setup in that case so PlayCanvas doesn't always-cull an "empty" batch.
 */
export function computeInstanceAabb(
  matrices: Float32Array,
  count:    number,
  margin:   number,
): pc.BoundingBox {
  const aabb = new pc.BoundingBox()
  if (count === 0) return aabb
  let minX = Infinity,  minY = Infinity,  minZ = Infinity
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity
  for (let i = 0; i < count; i++) {
    const o = i * 16
    const x = matrices[o + 12]
    const y = matrices[o + 13]
    const z = matrices[o + 14]
    if (x < minX) minX = x
    if (x > maxX) maxX = x
    if (y < minY) minY = y
    if (y > maxY) maxY = y
    if (z < minZ) minZ = z
    if (z > maxZ) maxZ = z
  }
  aabb.center.set((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2)
  aabb.halfExtents.set(
    (maxX - minX) / 2 + margin,
    (maxY - minY) / 2 + margin,
    (maxZ - minZ) / 2 + margin,
  )
  return aabb
}
