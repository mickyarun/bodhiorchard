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
 * ForestLake — A natural circular pond with lily pads and fish,
 * surrounded by a dense cluster of pine trees forming a mini-forest.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { FOREST_TREES } from '../assets/AssetManifest'
import { randRange } from '../utils/MathUtils'

const LAKE_RADIUS = 7
const CAUSTIC_SIZE = 128
const FOREST_TREE_COUNT = 35  // dense mixed forest
const FOREST_RADIUS = 50     // wide forest spread

const LILY_GLBS = [
  'assets/garden/lily_large.glb',
  'assets/garden/lily_small.glb',
]
const FISH_GLB = 'assets/garden/animal-fish.glb'

export class ForestLake {
  private root: pc.Entity | null = null
  private surface: pc.Entity | null = null
  private fishEntity: pc.Entity | null = null
  private time = 0
  private causticTexture: pc.Texture | null = null
  private waterMaterial: pc.StandardMaterial | null = null
  private shoreMaterial: pc.StandardMaterial | null = null
  private bedMaterial: pc.StandardMaterial | null = null

  async build(
    app: Application,
    loader: AssetLoader,
    cx: number,
    cz: number,
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('ForestLake')
    this.root.setPosition(cx, 0, cz)

    // Shore ring — sandy earth disc
    const shore = new pc.Entity('LakeShore')
    shore.addComponent('render', { type: 'cylinder' })
    const shoreR = LAKE_RADIUS * 1.3
    shore.setLocalScale(shoreR * 2, 0.05, shoreR * 2)
    shore.setLocalPosition(0, -0.1, 0)
    this.shoreMaterial = new pc.StandardMaterial()
    this.shoreMaterial.diffuse = new pc.Color(0.42, 0.38, 0.28)
    this.shoreMaterial.metalness = 0
    this.shoreMaterial.gloss = 0.05
    this.shoreMaterial.update()
    shore.render!.meshInstances[0].material = this.shoreMaterial
    this.root.addChild(shore)

    // Lake bed — dark earth disc
    const bed = new pc.Entity('LakeBed')
    bed.addComponent('render', { type: 'cylinder' })
    bed.setLocalScale(LAKE_RADIUS * 2, 0.04, LAKE_RADIUS * 2)
    bed.setLocalPosition(0, -0.15, 0)
    this.bedMaterial = new pc.StandardMaterial()
    this.bedMaterial.diffuse = new pc.Color(0.12, 0.1, 0.06)
    this.bedMaterial.metalness = 0
    this.bedMaterial.gloss = 0.02
    this.bedMaterial.update()
    bed.render!.meshInstances[0].material = this.bedMaterial
    this.root.addChild(bed)

    // Water surface — circular disc
    this.surface = new pc.Entity('LakeWater')
    this.surface.addComponent('render', { type: 'cylinder' })
    this.surface.setLocalScale(LAKE_RADIUS * 2, 0.02, LAKE_RADIUS * 2)
    this.surface.setLocalPosition(0, 0.05, 0)

    this.causticTexture = this.createCausticTexture(app.app.graphicsDevice)
    this.waterMaterial = new pc.StandardMaterial()
    this.waterMaterial.diffuse = new pc.Color(0.08, 0.35, 0.32)
    this.waterMaterial.emissive = new pc.Color(0.04, 0.18, 0.22)
    this.waterMaterial.diffuseMap = this.causticTexture
    this.waterMaterial.metalness = 0.1
    this.waterMaterial.gloss = 0.85
    this.waterMaterial.opacity = 0.8
    this.waterMaterial.blendType = pc.BLEND_NORMAL
    this.waterMaterial.cull = pc.CULLFACE_NONE
    this.waterMaterial.depthWrite = false
    this.waterMaterial.update()

    this.surface.render!.meshInstances[0].material = this.waterMaterial
    this.root.addChild(this.surface)

    // Lily pads floating on the water
    const lilyAssets = await loader.loadBatch(LILY_GLBS)
    for (let i = 0; i < 6; i++) {
      const asset = lilyAssets[Math.floor(Math.random() * lilyAssets.length)]
      const lily = loader.instance(asset)
      const angle = Math.random() * Math.PI * 2
      const dist = randRange(1, LAKE_RADIUS * 0.7)
      lily.setLocalPosition(
        Math.cos(angle) * dist,
        0.08,
        Math.sin(angle) * dist,
      )
      lily.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(1.5, 3.0)
      lily.setLocalScale(s, s, s)
      this.root.addChild(lily)
    }

    // Fish near the water edge
    const fishAsset = await loader.load(FISH_GLB)
    this.fishEntity = loader.instance(fishAsset)
    this.fishEntity.setLocalPosition(LAKE_RADIUS * 0.3, 0.08, 0)
    this.fishEntity.setLocalScale(0.5, 0.5, 0.5)
    this.root.addChild(this.fishEntity)

    // Dense mixed forest cluster surrounding the lake
    const forestAssets = await loader.loadBatch(FOREST_TREES)
    for (let i = 0; i < FOREST_TREE_COUNT; i++) {
      const angle = (i / FOREST_TREE_COUNT) * Math.PI * 2 + randRange(-0.4, 0.4)
      const dist = LAKE_RADIUS * 1.5 + randRange(2, FOREST_RADIUS - LAKE_RADIUS)
      const tx = Math.cos(angle) * dist
      const tz = Math.sin(angle) * dist

      const asset = forestAssets[Math.floor(Math.random() * forestAssets.length)]
      const tree = loader.instance(asset)
      tree.setLocalPosition(tx, 0, tz)
      tree.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(3, 8)
      tree.setLocalScale(s, s, s)
      this.root.addChild(tree)
    }

    app.root.addChild(this.root)
    return this.root
  }

  update(dt: number): void {
    if (!this.surface || !this.waterMaterial) return
    this.time += dt

    // Gentle wave bobbing
    const y = 0.05 + Math.sin(this.time * 0.8) * 0.03
    this.surface.setLocalPosition(0, y, 0)

    // Animate caustic texture offset
    this.waterMaterial.diffuseMapOffset.x = Math.sin(this.time * 0.2) * 0.08
    this.waterMaterial.diffuseMapOffset.y = Math.cos(this.time * 0.15) * 0.06
    this.waterMaterial.update()

    // Fish gently bobs and circles
    if (this.fishEntity) {
      const fx = Math.cos(this.time * 0.3) * LAKE_RADIUS * 0.4
      const fz = Math.sin(this.time * 0.3) * LAKE_RADIUS * 0.3
      const fy = 0.1 + Math.sin(this.time * 1.5) * 0.05
      this.fishEntity.setLocalPosition(fx, fy, fz)
      // Face the direction of movement
      const yaw = -this.time * 0.3 * (180 / Math.PI) + 90
      this.fishEntity.setLocalEulerAngles(0, yaw, 0)
    }
  }

  private createCausticTexture(device: pc.GraphicsDevice): pc.Texture {
    const S = CAUSTIC_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = S
    canvas.height = S
    const ctx = canvas.getContext('2d')!

    ctx.fillStyle = 'rgb(20, 70, 65)'
    ctx.fillRect(0, 0, S, S)

    for (let i = 0; i < 80; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const r = 3 + Math.random() * 15
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${60 + Math.random() * 40}, ${130 + Math.random() * 50}, ${120 + Math.random() * 40}, ${0.08 + Math.random() * 0.12})`
      ctx.fill()
    }

    for (let i = 0; i < 60; i++) {
      const x1 = Math.random() * S
      const y1 = Math.random() * S
      const angle = Math.random() * Math.PI * 2
      const len = 5 + Math.random() * 20
      ctx.strokeStyle = `rgba(${80 + Math.random() * 50}, ${160 + Math.random() * 40}, ${140 + Math.random() * 30}, ${0.06 + Math.random() * 0.1})`
      ctx.lineWidth = 0.5 + Math.random() * 1.5
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      const cpx = x1 + Math.cos(angle) * len * 0.5 + (Math.random() - 0.5) * 10
      const cpy = y1 + Math.sin(angle) * len * 0.5
      ctx.quadraticCurveTo(cpx, cpy, x1 + Math.cos(angle) * len, y1 + Math.sin(angle) * len)
      ctx.stroke()
    }

    const texture = new pc.Texture(device, {
      width: S,
      height: S,
      format: pc.PIXELFORMAT_RGBA8,
      addressU: pc.ADDRESS_REPEAT,
      addressV: pc.ADDRESS_REPEAT,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
    })
    const pixels = texture.lock()
    pixels.set(ctx.getImageData(0, 0, S, S).data)
    texture.unlock()
    return texture
  }

  destroy(): void {
    this.root?.destroy()
    this.root = null
    this.surface = null
    this.fishEntity = null
    this.causticTexture?.destroy()
    this.causticTexture = null
    this.waterMaterial?.destroy()
    this.waterMaterial = null
    this.shoreMaterial?.destroy()
    this.shoreMaterial = null
    this.bedMaterial?.destroy()
    this.bedMaterial = null
  }
}
