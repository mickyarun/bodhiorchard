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
  mi.setInstancing(vb)
  // Per-instance positions live in the VertexBuffer; the MeshInstance-level
  // AABB is the base mesh alone and would incorrectly cull the whole group
  // if left enabled. Relying on camera far-clip + scene fog instead.
  mi.cull = false

  const entity = new pc.Entity(name)
  entity.addComponent('render', {
    meshInstances:  [mi],
    castShadows:    opts.castShadows    ?? false,
    receiveShadows: opts.receiveShadows ?? false,
  })

  return { entity, vb }
}
