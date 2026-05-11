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
 * GroundBuilder — procedural dirt patch with grass ring.
 *
 * Creates a textured plane from a procedural canvas-to-texture
 * radial gradient (dirt center → grass edge). All geometry is procedural.
 */
import * as pc from 'playcanvas'

const TEXTURE_SIZE = 256
const Z_FIGHT_OFFSET = 0.001

export class GroundBuilder {
  private app: pc.AppBase
  private groundEntity: pc.Entity | null = null
  private groundTexture: pc.Texture | null = null
  private groundMaterial: pc.StandardMaterial | null = null

  constructor(app: pc.AppBase) {
    this.app = app
  }

  build(parent: pc.Entity, radius: number): void {
    this.groundTexture = this.createGroundTexture()

    // Ground needs a texture map, so we create it directly (not via MaterialFactory
    // which only handles solid colors). Tracked for cleanup in destroy().
    this.groundMaterial = new pc.StandardMaterial()
    this.groundMaterial.diffuseMap = this.groundTexture
    this.groundMaterial.metalness = 0
    this.groundMaterial.gloss = 0.1
    this.groundMaterial.update()

    this.groundEntity = new pc.Entity('Ground')
    this.groundEntity.addComponent('render', { type: 'plane' })
    this.groundEntity.render!.meshInstances[0].material = this.groundMaterial
    this.groundEntity.setLocalScale(radius * 2, 1, radius * 2)
    this.groundEntity.setPosition(0, Z_FIGHT_OFFSET, 0)
    parent.addChild(this.groundEntity)
  }

  private createGroundTexture(): pc.Texture {
    const size = TEXTURE_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')!

    const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    gradient.addColorStop(0, '#6B4423')
    gradient.addColorStop(0.3, '#8B6914')
    gradient.addColorStop(0.6, '#5A7D2B')
    gradient.addColorStop(0.8, '#4A8B2F')
    gradient.addColorStop(1.0, '#3D7A28')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)

    // Organic noise
    const imgData = ctx.getImageData(0, 0, size, size)
    for (let i = 0; i < imgData.data.length; i += 4) {
      const noise = (Math.random() - 0.5) * 15
      imgData.data[i] = Math.max(0, Math.min(255, imgData.data[i] + noise))
      imgData.data[i + 1] = Math.max(0, Math.min(255, imgData.data[i + 1] + noise))
      imgData.data[i + 2] = Math.max(0, Math.min(255, imgData.data[i + 2] + noise))
    }
    // Reuse imgData directly — avoids a second 262KB getImageData allocation
    const texture = new pc.Texture(this.app.graphicsDevice, {
      width: size, height: size,
      format: pc.PIXELFORMAT_RGBA8,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
    })
    const source = texture.lock()
    for (let i = 0; i < imgData.data.length; i++) source[i] = imgData.data[i]
    texture.unlock()
    return texture
  }

  destroy(): void {
    this.groundEntity?.destroy(); this.groundEntity = null
    this.groundMaterial?.destroy(); this.groundMaterial = null
    this.groundTexture?.destroy(); this.groundTexture = null
  }
}
