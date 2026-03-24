/**
 * GroundSystem — Textured terrain plane with procedural grass texture.
 *
 * Generates a canvas-based grass texture with color variation and noise
 * to eliminate visible tiling lines. Uses StandardMaterial with the
 * generated diffuseMap for a natural grassy appearance.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { MaterialFactory } from '../rendering/MaterialFactory'

const TEXTURE_SIZE = 512

export class GroundSystem {
  private entity: pc.Entity | null = null
  private texture: pc.Texture | null = null
  private material: pc.StandardMaterial | null = null

  build(app: Application, _materials: MaterialFactory): pc.Entity {
    this.entity = new pc.Entity('Ground')
    this.entity.addComponent('render', { type: 'plane' })
    this.entity.setLocalScale(600, 1, 600)
    this.entity.setPosition(0, 0, 0)

    // Generate procedural grass texture
    this.texture = this.createGrassTexture(app.app.graphicsDevice)

    this.material = new pc.StandardMaterial()
    this.material.diffuseMap = this.texture
    this.material.diffuse = new pc.Color(1, 1, 1)
    this.material.metalness = 0
    this.material.gloss = 0.05
    this.material.update()

    const meshInstance = this.entity.render!.meshInstances[0]
    meshInstance.material = this.material

    app.root.addChild(this.entity)
    return this.entity
  }

  /** Generate a grass-like texture with subtle variation using Canvas2D. */
  private createGrassTexture(device: pc.GraphicsDevice): pc.Texture {
    const canvas = document.createElement('canvas')
    canvas.width = TEXTURE_SIZE
    canvas.height = TEXTURE_SIZE
    const ctx = canvas.getContext('2d')!

    // Base green fill
    ctx.fillStyle = 'rgb(58, 110, 40)'
    ctx.fillRect(0, 0, TEXTURE_SIZE, TEXTURE_SIZE)

    // Layer 1: large patches of color variation
    for (let i = 0; i < 40; i++) {
      const x = Math.random() * TEXTURE_SIZE
      const y = Math.random() * TEXTURE_SIZE
      const r = 30 + Math.random() * 60
      const shade = Math.random()
      const green = shade < 0.5
        ? `rgba(45, ${90 + Math.random() * 30}, 30, 0.3)`
        : `rgba(70, ${120 + Math.random() * 25}, 50, 0.25)`
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = green
      ctx.fill()
    }

    // Layer 2: small grass blade strokes
    for (let i = 0; i < 2000; i++) {
      const x = Math.random() * TEXTURE_SIZE
      const y = Math.random() * TEXTURE_SIZE
      const len = 2 + Math.random() * 6
      const angle = -Math.PI / 2 + (Math.random() - 0.5) * 0.8
      const g = 80 + Math.random() * 60
      const r = 30 + Math.random() * 35
      ctx.strokeStyle = `rgba(${r}, ${g}, ${Math.floor(r * 0.6)}, 0.5)`
      ctx.lineWidth = 0.5 + Math.random() * 1
      ctx.beginPath()
      ctx.moveTo(x, y)
      ctx.lineTo(x + Math.cos(angle) * len, y + Math.sin(angle) * len)
      ctx.stroke()
    }

    // Layer 3: tiny light speckles for sparkle
    for (let i = 0; i < 500; i++) {
      const x = Math.random() * TEXTURE_SIZE
      const y = Math.random() * TEXTURE_SIZE
      ctx.fillStyle = `rgba(${100 + Math.random() * 40}, ${140 + Math.random() * 40}, ${60 + Math.random() * 20}, 0.15)`
      ctx.fillRect(x, y, 1, 1)
    }

    const texture = new pc.Texture(device, {
      width: TEXTURE_SIZE,
      height: TEXTURE_SIZE,
      format: pc.PIXELFORMAT_RGBA8,
      addressU: pc.ADDRESS_REPEAT,
      addressV: pc.ADDRESS_REPEAT,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      anisotropy: 4,
    })

    const pixels = texture.lock()
    const imageData = ctx.getImageData(0, 0, TEXTURE_SIZE, TEXTURE_SIZE)
    pixels.set(imageData.data)
    texture.unlock()

    return texture
  }

  destroy(_materials?: MaterialFactory): void {
    if (this.entity) {
      this.entity.destroy()
      this.entity = null
    }
    if (this.texture) {
      this.texture.destroy()
      this.texture = null
    }
    if (this.material) {
      this.material.destroy()
      this.material = null
    }
  }
}
