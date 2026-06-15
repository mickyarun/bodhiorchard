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
 * CloudSystem — Puffy clouds from clustered sphere primitives.
 *
 * Each cloud is a group of 4-7 overlapping spheres at slightly different
 * offsets and scales, creating a cotton-ball look. Translucent emissive
 * material makes them glow softly against the sky. Slowly drifts across
 * the world and wraps around when leaving bounds.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { randRange } from '../utils/MathUtils'
import { Theme } from '../rendering/Theme'
import { createInstancedEntity, computeInstanceAabb } from '../treetest/instancing'

const CLOUD_COUNT = 12
const ALTITUDE_MIN = 100
const ALTITUDE_MAX = 160
const SPREAD = 300
const DRIFT_SPEED = 1.2

/** Number of spheres per cloud cluster. */
const PUFFS_MIN = 4
const PUFFS_MAX = 7

interface CloudInstance {
  entity: pc.Entity
  driftX: number
  driftZ: number
}

export class CloudSystem {
  private root: pc.Entity | null = null
  private clouds: CloudInstance[] = []
  private vbs: pc.VertexBuffer[] = []
  private sphereMesh: pc.Mesh | null = null

  build(app: Application, materials: MaterialFactory): pc.Entity {
    this.root = new pc.Entity('CloudSystem')
    // Shared unit sphere for every instanced puff batch (destroyed with us).
    this.sphereMesh = pc.Mesh.fromGeometry(
      app.app.graphicsDevice, new pc.SphereGeometry(),
    )

    const cloudMat = materials.getColor('cloud', 1, 1, 1, {
      opacity: Theme.CLOUD.opacity,
      emissive: [
        Theme.CLOUD.emissive[0] / 255,
        Theme.CLOUD.emissive[1] / 255,
        Theme.CLOUD.emissive[2] / 255,
      ],
    })

    for (let i = 0; i < CLOUD_COUNT; i++) {
      const cloud = this.buildCloudCluster(i, cloudMat, app.app.graphicsDevice)
      cloud.setPosition(
        randRange(-SPREAD, SPREAD),
        randRange(ALTITUDE_MIN, ALTITUDE_MAX),
        randRange(-SPREAD, SPREAD),
      )
      this.root.addChild(cloud)
      this.clouds.push({
        entity: cloud,
        driftX: randRange(-1, 1) * DRIFT_SPEED,
        driftZ: randRange(-1, 1) * DRIFT_SPEED * 0.4,
      })
    }

    app.root.addChild(this.root)
    return this.root
  }

  /**
   * Create a single cloud as ONE instanced draw of overlapping sphere
   * "puffs". Instance matrices are LOCAL to the cluster group — the
   * renderer composes group.world × instance matrix, so the per-frame
   * drift in update() still moves the whole cloud. Non-uniform puff
   * scale (vertical flattening) is baked straight into each matrix,
   * which the ScatterTransform-based helper can't express.
   */
  private buildCloudCluster(
    index: number, material: pc.Material, device: pc.GraphicsDevice,
  ): pc.Entity {
    const group = new pc.Entity(`Cloud_${index}`)
    const puffCount = Math.floor(randRange(PUFFS_MIN, PUFFS_MAX + 1))

    // Base scale for the whole cloud (variety between clouds)
    const cloudScale = randRange(1.0, 1.8)

    const matrices = new Float32Array(puffCount * 16)
    const mat = new pc.Mat4()
    const pos = new pc.Vec3()
    const rot = new pc.Quat()
    const scl = new pc.Vec3()
    for (let p = 0; p < puffCount; p++) {
      // Spread puffs along the X axis (elongated), less on Y/Z
      pos.set(
        randRange(-8, 8) * cloudScale,
        randRange(-1.5, 1.5) * cloudScale,
        randRange(-4, 4) * cloudScale,
      )
      // Each puff has slightly different scale for organic shape
      const s = randRange(4, 9) * cloudScale
      scl.set(s, s * randRange(0.4, 0.7), s * randRange(0.7, 1.0))
      mat.setTRS(pos, rot, scl)
      matrices.set(mat.data, p * 16)
    }

    // Margin covers the largest puff's half-extent (unit sphere radius 0.5
    // × max scale ~16) so frustum culling never pops a visible cloud.
    const aabb = computeInstanceAabb(matrices, puffCount, 9 * cloudScale)
    const { entity, vb } = createInstancedEntity(
      device, this.sphereMesh!, material, matrices, puffCount,
      `CloudPuffs_${index}`, { aabb },
    )
    group.addChild(entity)
    this.vbs.push(vb)

    return group
  }

  update(dt: number): void {
    for (const cloud of this.clouds) {
      const pos = cloud.entity.getPosition()
      let x = pos.x + cloud.driftX * dt
      let z = pos.z + cloud.driftZ * dt

      if (x > SPREAD) x -= SPREAD * 2
      if (x < -SPREAD) x += SPREAD * 2
      if (z > SPREAD) z -= SPREAD * 2
      if (z < -SPREAD) z += SPREAD * 2

      cloud.entity.setPosition(x, pos.y, z)
    }
  }

  destroy(): void {
    this.clouds = []
    for (const vb of this.vbs) vb.destroy()
    this.vbs = []
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
    if (this.sphereMesh) {
      this.sphereMesh.vertexBuffer?.destroy()
      this.sphereMesh.indexBuffer?.[0]?.destroy()
      this.sphereMesh = null
    }
  }
}
