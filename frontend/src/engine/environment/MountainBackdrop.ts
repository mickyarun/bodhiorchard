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
 * MountainBackdrop — Mountain range along one edge of the world.
 *
 * Places mountain GLBs at the far end of the world to create
 * a scenic Eastern Ghats-style backdrop behind the pine forest.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { MOUNTAINS } from '../assets/AssetManifest'
import { randRange } from '../utils/MathUtils'

/** Distance from center where mountains start — distant horizon backdrop. */
const MOUNTAIN_DISTANCE = 280
/** How many mountain instances to place in the cluster. */
const MOUNTAIN_COUNT = 6

export class MountainBackdrop {
  private root: pc.Entity | null = null

  async build(app: Application, loader: AssetLoader): Promise<pc.Entity> {
    this.root = new pc.Entity('MountainBackdrop')

    const assets = await loader.loadBatch(MOUNTAINS)

    // Place mountains in a tight cluster on one side (north-west, like Eastern Ghats)
    // Narrow arc of ~60 degrees for a single mountain range
    const centerAngle = -Math.PI * 0.4  // north-west direction
    const arcSpread = Math.PI * 0.35    // ~63 degree spread
    const arcStart = centerAngle - arcSpread / 2
    const arcEnd = centerAngle + arcSpread / 2
    const arcStep = (arcEnd - arcStart) / (MOUNTAIN_COUNT - 1)

    for (let i = 0; i < MOUNTAIN_COUNT; i++) {
      const angle = arcStart + i * arcStep
      // Vary the distance slightly for natural feel
      const dist = MOUNTAIN_DISTANCE + randRange(-8, 12)
      const x = Math.sin(angle) * dist
      const z = Math.cos(angle) * dist

      const asset = assets[Math.floor(Math.random() * assets.length)]
      const instance = loader.instance(asset)
      instance.setPosition(x, 0, z)
      instance.setLocalEulerAngles(0, randRange(0, 360), 0)

      // Large scale — distant horizon needs to be massive to be visible
      const s = randRange(30, 60)
      // Vary height for natural mountain range silhouette
      const sy = s * randRange(0.8, 1.5)
      instance.setLocalScale(s, sy, s)

      this.root.addChild(instance)
    }

    app.root.addChild(this.root)
    return this.root
  }

  destroy(): void {
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
