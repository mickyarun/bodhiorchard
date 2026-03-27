/**
 * GroundSystem — Textured terrain plane with procedural grass texture
 * and sand/dirt disc overlays at building zones.
 *
 * The base is a 600×600 grass plane. Building zones (housing, pool,
 * coffee bar, etc.) get circular overlay planes with zone-specific
 * textures that blend into the grass via radial alpha fade.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { WorldZone } from '../world/WorldLayout'

const TEXTURE_SIZE = 1024
const OVERLAY_TEX_SIZE = 256

// Zone-specific ground colors
const ZONE_COLORS: Record<string, { r: number; g: number; b: number }> = {
  pool:       { r: 210, g: 185, b: 140 },  // warm sand
  housing:    { r: 190, g: 170, b: 130 },  // sandy dirt
  coffee_bar: { r: 160, g: 140, b: 110 },  // packed earth
  cafeteria:  { r: 165, g: 145, b: 115 },  // packed earth
  pavilion:   { r: 170, g: 165, b: 155 },  // stone paving
}

export class GroundSystem {
  private entity: pc.Entity | null = null
  private texture: pc.Texture | null = null
  private material: pc.StandardMaterial | null = null
  private overlayEntities: pc.Entity[] = []
  private overlayTextures: pc.Texture[] = []
  private overlayMaterials: pc.StandardMaterial[] = []

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

  /**
   * Add sand/dirt disc overlays at building zone positions.
   * Call after build() and after WorldLayout zones are defined.
   */
  addZoneOverlays(app: Application, zones: readonly WorldZone[]): void {
    for (const zone of zones) {
      const colors = ZONE_COLORS[zone.name]
      if (!colors) continue  // skip orchard — stays grass

      const entity = new pc.Entity(`Ground_${zone.name}`)
      entity.addComponent('render', { type: 'plane' })
      // Diameter = radius × 2, with slight padding for soft edge
      const diameter = zone.radius * 2.4
      entity.setLocalScale(diameter, 1, diameter)
      entity.setPosition(zone.x, 0.02, zone.z)  // just above grass

      const texture = this.createZoneTexture(app.app.graphicsDevice, colors)
      const material = new pc.StandardMaterial()
      material.diffuseMap = texture
      material.diffuse = new pc.Color(1, 1, 1)
      material.metalness = 0
      material.gloss = 0.08
      material.opacityMap = texture        // alpha channel controls blend
      material.alphaTest = 0.01            // discard fully transparent pixels
      material.blendType = pc.BLEND_NORMAL
      material.depthWrite = false          // avoid z-fighting artifacts
      material.cull = pc.CULLFACE_NONE
      material.update()

      entity.render!.meshInstances[0].material = material
      app.root.addChild(entity)

      this.overlayEntities.push(entity)
      this.overlayTextures.push(texture)
      this.overlayMaterials.push(material)
    }
  }

  /** Generate a grass-like texture with subtle variation using Canvas2D. */
  private createGrassTexture(device: pc.GraphicsDevice): pc.Texture {
    const S = TEXTURE_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = S
    canvas.height = S
    const ctx = canvas.getContext('2d')!

    // Base green fill — slightly warmer
    ctx.fillStyle = 'rgb(62, 120, 42)'
    ctx.fillRect(0, 0, S, S)

    // Layer 1: large patches of color variation
    for (let i = 0; i < 50; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const r = 30 + Math.random() * 70
      const shade = Math.random()
      const green = shade < 0.4
        ? `rgba(45, ${90 + Math.random() * 30}, 30, 0.3)`
        : shade < 0.8
        ? `rgba(70, ${120 + Math.random() * 25}, 50, 0.25)`
        : `rgba(55, ${100 + Math.random() * 20}, 35, 0.2)` // mid tone
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = green
      ctx.fill()
    }

    // Layer 1b: occasional brown/earth patches for natural variation
    for (let i = 0; i < 8; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const r = 15 + Math.random() * 30
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${100 + Math.random() * 30}, ${85 + Math.random() * 20}, ${50 + Math.random() * 20}, 0.12)`
      ctx.fill()
    }

    // Layer 2: dense grass blade strokes
    for (let i = 0; i < 4000; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
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

    // Layer 3: light speckles for sparkle
    for (let i = 0; i < 1000; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      ctx.fillStyle = `rgba(${100 + Math.random() * 40}, ${140 + Math.random() * 40}, ${60 + Math.random() * 20}, 0.15)`
      ctx.fillRect(x, y, 1, 1)
    }

    const texture = new pc.Texture(device, {
      width: S,
      height: S,
      format: pc.PIXELFORMAT_RGBA8,
      addressU: pc.ADDRESS_REPEAT,
      addressV: pc.ADDRESS_REPEAT,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      anisotropy: 4,
    })

    const pixels = texture.lock()
    const imageData = ctx.getImageData(0, 0, S, S)
    pixels.set(imageData.data)
    texture.unlock()

    return texture
  }

  /** Generate a zone-specific ground texture with radial alpha fade. */
  private createZoneTexture(
    device: pc.GraphicsDevice,
    color: { r: number; g: number; b: number },
  ): pc.Texture {
    const S = OVERLAY_TEX_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = S
    canvas.height = S
    const ctx = canvas.getContext('2d')!

    const cx = S / 2
    const cy = S / 2
    const maxR = S / 2

    // Base fill
    ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`
    ctx.fillRect(0, 0, S, S)

    // Noise patches for variation
    for (let i = 0; i < 30; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const r = 10 + Math.random() * 30
      const dr = Math.floor((Math.random() - 0.5) * 25)
      const dg = Math.floor((Math.random() - 0.5) * 20)
      const db = Math.floor((Math.random() - 0.5) * 15)
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${color.r + dr}, ${color.g + dg}, ${color.b + db}, 0.3)`
      ctx.fill()
    }

    // Small grain/pebble dots
    for (let i = 0; i < 400; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const dr = Math.floor((Math.random() - 0.5) * 40)
      ctx.fillStyle = `rgba(${color.r + dr}, ${color.g + dr * 0.8}, ${color.b + dr * 0.6}, 0.25)`
      ctx.fillRect(x, y, 1 + Math.random(), 1 + Math.random())
    }

    // Apply radial alpha fade: opaque center → transparent edge
    const imageData = ctx.getImageData(0, 0, S, S)
    const data = imageData.data
    for (let y = 0; y < S; y++) {
      for (let x = 0; x < S; x++) {
        const dx = x - cx
        const dy = y - cy
        const dist = Math.sqrt(dx * dx + dy * dy) / maxR  // 0 at center, 1 at edge

        // Fade starts at 55% radius, fully transparent at 100%
        let alpha: number
        if (dist < 0.55) {
          alpha = 1.0
        } else if (dist < 1.0) {
          // Smooth cubic fade
          const t = (dist - 0.55) / 0.45
          alpha = 1.0 - t * t * (3 - 2 * t)
        } else {
          alpha = 0
        }

        const idx = (y * S + x) * 4
        data[idx + 3] = Math.floor(data[idx + 3] * alpha)
      }
    }
    // Write modified pixel data directly to texture — skip putImageData + re-read round-trip
    const texture = new pc.Texture(device, {
      width: S,
      height: S,
      format: pc.PIXELFORMAT_RGBA8,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      anisotropy: 2,
    })

    const pixels = texture.lock()
    pixels.set(data)
    texture.unlock()

    return texture
  }

  destroy(_materials?: MaterialFactory): void {
    for (const entity of this.overlayEntities) entity.destroy()
    for (const tex of this.overlayTextures) tex.destroy()
    for (const mat of this.overlayMaterials) mat.destroy()
    this.overlayEntities = []
    this.overlayTextures = []
    this.overlayMaterials = []

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
