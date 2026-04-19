// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * ScaledFurniture — place GLBs with world-space AABB auto-fit.
 *
 * Problem this solves:
 *   BuildingFactory.placeFurnitureCentered uses each mesh's RAW `mesh.aabb`,
 *   which is the mesh's own model-space bounding box. That works for Kenney
 *   assets because Kenney GLBs have identity node transforms — raw AABB ==
 *   rendered size. It fails for packs like Coffeehouse Lounge where the GLB
 *   nodes bake in scale transforms: the raw mesh is tiny, but once the node
 *   scale is applied the rendered model is 10×–100× larger. Dividing by the
 *   wrong denominator gives the wrong scale, and items come out comically big.
 *
 * Fix:
 *   After parenting the model into the scene graph, force a hierarchy sync so
 *   `meshInstance.aabb` (world-space) reflects every node transform in the
 *   GLB. We then fit on that true world-space extent, making a single uniform
 *   `maxDim` target work for every asset regardless of authoring convention.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { AssetLoader } from '../assets/AssetLoader'

export interface ScaledPlacement {
  /** Wrapper entity, already parented, positioned, rotated and scaled. */
  entity: pc.Entity
  /** Final world-space size of the rendered model after scaling. */
  size: { x: number; y: number; z: number }
}

export interface ScaledFurnitureOpts {
  /**
   * Target length of the longest axis in world metres. Omit to skip scaling
   * — used for Kenney assets that already render at 1m = 1 unit.
   */
  maxDim?: number
  /** Yaw rotation in degrees around the Y axis. */
  yaw?: number
}

/**
 * Instance a GLB under `parent`, auto-scale so its longest world-space axis
 * matches `maxDim`, and anchor the visual bottom-centre at (x, y, z).
 *
 * Uses world-space mesh AABB (post-sync) so packs with baked node scale work
 * the same as packs without. Uniform scale preserves the model's aspect ratio.
 */
export async function placeScaledFurniture(
  loader: AssetLoader,
  app: Application,
  parent: pc.Entity,
  assetPath: string,
  x: number, y: number, z: number,
  opts: ScaledFurnitureOpts = {},
): Promise<ScaledPlacement> {
  const yaw = opts.yaw ?? 0

  const asset = await loader.load(assetPath)
  const model = loader.instance(asset)

  // Parent at origin so the world AABB equals the model's native rendered
  // extent (any wrapper transform would confound the measurement).
  const wrapper = new pc.Entity('ScaledFurniture')
  wrapper.addChild(model)
  parent.addChild(wrapper)

  // Force transforms + bounds to update so meshInstance.aabb is valid.
  // Reads mi.aabb instead of mi.mesh.aabb — this is the whole point.
  app.app.root.syncHierarchy()

  const meshes = collectMeshInstances(model)
  if (meshes.length === 0) {
    wrapper.setLocalPosition(x, y, z)
    if (yaw !== 0) wrapper.setLocalEulerAngles(0, yaw, 0)
    return { entity: wrapper, size: { x: 0, y: 0, z: 0 } }
  }

  const worldBox = unionWorldAabb(meshes)
  const min = worldBox.getMin()
  const max = worldBox.getMax()
  const nativeW = max.x - min.x
  const nativeH = max.y - min.y
  const nativeD = max.z - min.z
  const nativeMax = Math.max(nativeW, nativeH, nativeD)
  const scale = opts.maxDim !== undefined && nativeMax > 1e-4
    ? opts.maxDim / nativeMax
    : 1

  // Offset the model inside the wrapper so that after we apply the wrapper
  // scale, the model's XZ centre lands on (0,0) and its Y min lands on 0.
  // The wrapper is currently at origin with no scale, so worldBox.center is
  // exactly the offset we need to negate.
  const centre = worldBox.center
  model.setLocalPosition(-centre.x, -min.y, -centre.z)

  wrapper.setLocalScale(scale, scale, scale)
  wrapper.setLocalPosition(x, y, z)
  if (yaw !== 0) wrapper.setLocalEulerAngles(0, yaw, 0)

  return {
    entity: wrapper,
    size: { x: nativeW * scale, y: nativeH * scale, z: nativeD * scale },
  }
}

function collectMeshInstances(entity: pc.Entity): pc.MeshInstance[] {
  const renders = entity.findComponents('render') as pc.RenderComponent[]
  return renders.flatMap((rc) => rc.meshInstances)
}

function unionWorldAabb(meshes: pc.MeshInstance[]): pc.BoundingBox {
  const box = new pc.BoundingBox()
  box.copy(meshes[0].aabb)
  for (let i = 1; i < meshes.length; i++) box.add(meshes[i].aabb)
  return box
}
