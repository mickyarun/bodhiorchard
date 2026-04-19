// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CafeteriaScene — builds the cafeteria interior by loading a single GLB.
 *
 * Unlike CoffeeBarScene which composes ~80 individual furniture GLBs,
 * the cafeteria's entire interior (walls, tables, chairs, vending, food
 * display) ships as one self-contained model.
 *
 * The downloaded GLB has an arbitrary origin / orientation:
 *   - Its floor mesh doesn't necessarily sit at y=0
 *   - Its open side (where we want the door) may face any direction
 *
 * So we auto-center the GLB inside the room footprint by:
 *   1. Load + parent to a wrapper entity at origin
 *   2. Measure the combined world AABB after one sync
 *   3. Offset the model so (centerX, centerZ) lands on the room center and
 *      the floor (min.y) lands at y=0
 *   4. Apply CAFETERIA_YAW so the intended "front" faces +Z (toward the door)
 *
 * No `useLighting = false` overrides — the GLB's Principled BSDF materials
 * are lit by the engine's IBL + ACES + sRGB pipeline.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { AssetLoader } from '../assets/AssetLoader'
import { CAFETERIA } from '../assets/AssetManifest'
import type { CollisionBox } from '../housetest/CollisionSystem'
import {
  CAFETERIA_COLLISION,
  CAFETERIA_DEBUG_COLLISION,
  CAFETERIA_ROOM,
  CAFETERIA_SCALE,
  CAFETERIA_YAW,
  CAFETERIA_Y_OFFSET,
} from './SceneConfig'

export class CafeteriaScene {
  private loader: AssetLoader

  constructor(loader: AssetLoader) {
    this.loader = loader
  }

  async build(root: pc.Entity, app: Application): Promise<CollisionBox[]> {
    const asset = await this.loader.load(CAFETERIA.room)
    const model = this.loader.instance(asset)

    const wrapper = new pc.Entity('CafeteriaGLB')
    wrapper.addChild(model)
    root.addChild(wrapper)

    // Force transforms + bounds to update so meshInstance.aabb is valid.
    app.app.root.syncHierarchy()

    const meshes = this.collectMeshInstances(model)
    if (meshes.length > 0) {
      const worldBox = this.unionWorldAabb(meshes)
      const min = worldBox.getMin()
      const max = worldBox.getMax()
      const center = worldBox.center
      const s = CAFETERIA_SCALE

      // Scale the geometry, then offset so the *scaled* xz-center lands at
      // (0,0) and the *scaled* lowest vertex at y = -Y_OFFSET. Multiplying
      // center/min by the scale is critical: setLocalScale scales the mesh
      // but also scales the local-position offset, so the offset must live
      // in already-scaled space.
      model.setLocalScale(s, s, s)
      model.setLocalPosition(-s * center.x, -s * min.y - CAFETERIA_Y_OFFSET, -s * center.z)

      // Dev-only log so SceneConfig constants can be hand-tuned without
      // attaching a debugger. Silenced in production builds.
      if (import.meta.env.DEV) {
        const w = (max.x - min.x) * s
        const h = (max.y - min.y) * s
        const d = (max.z - min.z) * s
        console.log(
          `[CafeteriaScene] GLB native: ${(max.x-min.x).toFixed(2)}×${(max.y-min.y).toFixed(2)}×${(max.z-min.z).toFixed(2)} m\n` +
          `  after CAFETERIA_SCALE=${s}: ${w.toFixed(2)}×${h.toFixed(2)}×${d.toFixed(2)} m\n` +
          `  lowest vertex world Y = ${(-CAFETERIA_Y_OFFSET).toFixed(2)}  (character spawns at Y=0)\n` +
          `  CAFETERIA_ROOM is ${CAFETERIA_ROOM.width}×${CAFETERIA_ROOM.depth} — should match the scaled W×D above`,
        )
      }
    }

    // Position the wrapper at the room center and apply orientation yaw.
    wrapper.setLocalEulerAngles(0, CAFETERIA_YAW, 0)
    wrapper.setLocalPosition(CAFETERIA_ROOM.width / 2, 0, CAFETERIA_ROOM.depth / 2)

    if (CAFETERIA_DEBUG_COLLISION) {
      this.renderCollisionWireframes(root)
    }

    return CAFETERIA_COLLISION
  }

  /**
   * Renders each CollisionBox in CAFETERIA_COLLISION as a translucent red
   * box 1 m tall. Used during layout tuning — walk the character into each
   * wireframe and verify it wraps the intended GLB feature. Flip
   * CAFETERIA_DEBUG_COLLISION off in SceneConfig when done.
   */
  private renderCollisionWireframes(root: pc.Entity): void {
    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(1, 0.2, 0.2)
    mat.opacity = 0.35
    mat.blendType = pc.BLEND_NORMAL
    mat.depthWrite = false
    mat.cull = pc.CULLFACE_NONE
    mat.update()

    for (const box of CAFETERIA_COLLISION) {
      const w = box.maxX - box.minX
      const d = box.maxZ - box.minZ
      const cx = (box.maxX + box.minX) / 2
      const cz = (box.maxZ + box.minZ) / 2

      const e = new pc.Entity('DebugCollision')
      e.addComponent('render', { type: 'box' })
      e.setLocalScale(w, 1, d)
      e.setLocalPosition(cx, 0.5, cz)
      if (e.render) {
        for (const mi of e.render.meshInstances) mi.material = mat
      }
      root.addChild(e)
    }
  }

  private collectMeshInstances(entity: pc.Entity): pc.MeshInstance[] {
    const renders = entity.findComponents('render') as pc.RenderComponent[]
    return renders.flatMap((rc) => rc.meshInstances)
  }

  private unionWorldAabb(meshes: pc.MeshInstance[]): pc.BoundingBox {
    const box = new pc.BoundingBox()
    box.copy(meshes[0].aabb)
    for (let i = 1; i < meshes.length; i++) box.add(meshes[i].aabb)
    return box
  }
}
