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

  build(app: Application, materials: MaterialFactory): pc.Entity {
    this.root = new pc.Entity('CloudSystem')

    const cloudMat = materials.getColor('cloud', 1, 1, 1, {
      opacity: 0.45,
      emissive: [0.92, 0.94, 0.97],
    })

    for (let i = 0; i < CLOUD_COUNT; i++) {
      const cloud = this.buildCloudCluster(i, cloudMat)
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

  /** Create a single cloud from overlapping sphere "puffs". */
  private buildCloudCluster(index: number, material: pc.Material): pc.Entity {
    const group = new pc.Entity(`Cloud_${index}`)
    const puffCount = Math.floor(randRange(PUFFS_MIN, PUFFS_MAX + 1))

    // Base scale for the whole cloud (variety between clouds)
    const cloudScale = randRange(1.0, 1.8)

    for (let p = 0; p < puffCount; p++) {
      const puff = new pc.Entity(`Puff_${p}`)
      puff.addComponent('render', { type: 'sphere' })

      // Spread puffs along the X axis (elongated), less on Y/Z
      const px = randRange(-8, 8) * cloudScale
      const py = randRange(-1.5, 1.5) * cloudScale
      const pz = randRange(-4, 4) * cloudScale
      puff.setLocalPosition(px, py, pz)

      // Each puff has slightly different scale for organic shape
      const s = randRange(4, 9) * cloudScale
      const sy = s * randRange(0.4, 0.7) // flatten vertically
      puff.setLocalScale(s, sy, s * randRange(0.7, 1.0))

      puff.render!.meshInstances[0].material = material

      group.addChild(puff)
    }

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
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
