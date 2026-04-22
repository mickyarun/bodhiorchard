// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
  private pngTexture: pc.Texture | null = null
  private pngImage: HTMLImageElement | null = null

  build(app: Application, _materials: MaterialFactory): pc.Entity {
    this.entity = new pc.Entity('Ground')
    this.entity.addComponent('render', { type: 'plane' })
    this.entity.setLocalScale(600, 1, 600)
    this.entity.setPosition(0, 0, 0)

    // Procedural grass is the immediate fallback so the scene never flashes
    // untextured while the PNG asset loads.
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

    // Upgrade to the seamless grass JPG if available. Tiling chosen so blades
    // read at a natural size across the 600×600 plane.
    this.upgradeToGrassImage(app)

    return this.entity
  }

  /**
   * Swap the procedural grass for the seamless tileable grass.jpg.
   *
   * Loads via plain `Image` + `Texture.setSource(img)` rather than
   * `pc.Asset('texture')`. Two reasons:
   *   1. Full control over the Texture's initial options — mipmaps, filters,
   *      wrap modes, anisotropy — before the first upload. The asset handler
   *      requires string-keyed filter enums via its `data` arg, and mutating
   *      `minFilter` after the handler's upload is not guaranteed to
   *      regenerate the mip chain. Missing mipmaps makes the sampler read
   *      black per WebGL's texture-completeness rule — this is the
   *      "grass goes black on route re-mount" symptom.
   *   2. Avoids the asset-registry lifecycle entirely, so there is no
   *      stale-asset handoff across mounts.
   */
  private upgradeToGrassImage(app: Application): void {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    this.pngImage = img
    img.onload = () => {
      if (!this.material) return
      const tex = new pc.Texture(app.app.graphicsDevice, {
        name: 'grass',
        width: img.naturalWidth,
        height: img.naturalHeight,
        format: pc.PIXELFORMAT_RGBA8,
        mipmaps: true,
        addressU: pc.ADDRESS_REPEAT,
        addressV: pc.ADDRESS_REPEAT,
        minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
        magFilter: pc.FILTER_LINEAR,
        anisotropy: 8,
      })
      tex.setSource(img)
      this.pngTexture = tex
      this.material.diffuseMap = tex
      // 60 tiles across 600 units → 10 world units per tile. Matches the
      // low-poly stylized look in the target reference without visible seams.
      this.material.diffuseMapTiling = new pc.Vec2(60, 60)
      this.material.update()
    }
    img.onerror = (err) => {
      console.debug('[GroundSystem] grass.jpg failed to load, keeping procedural:', err)
    }
    img.src = '/assets/garden/grass.jpg'
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

    // Rich base green — darker, more natural
    ctx.fillStyle = 'rgb(48, 95, 32)'
    ctx.fillRect(0, 0, S, S)

    // Layer 1: large natural color patches (light/dark variation like real turf)
    for (let i = 0; i < 80; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const r = 20 + Math.random() * 80
      const shade = Math.random()
      let fill: string
      if (shade < 0.3) {
        // Dark shadow patches
        fill = `rgba(30, ${65 + Math.random() * 20}, 20, 0.35)`
      } else if (shade < 0.6) {
        // Mid green
        fill = `rgba(55, ${100 + Math.random() * 25}, 40, 0.3)`
      } else if (shade < 0.85) {
        // Warm yellow-green (sunlit)
        fill = `rgba(75, ${115 + Math.random() * 20}, 45, 0.25)`
      } else {
        // Bright highlights
        fill = `rgba(90, ${130 + Math.random() * 15}, 55, 0.2)`
      }
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = fill
      ctx.fill()
    }

    // Layer 1b: earth/soil patches peeking through
    for (let i = 0; i < 12; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const r = 8 + Math.random() * 20
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${85 + Math.random() * 25}, ${70 + Math.random() * 15}, ${40 + Math.random() * 15}, 0.1)`
      ctx.fill()
    }

    // Layer 2: grass clumps — multiple blades from same origin point
    for (let i = 0; i < 600; i++) {
      const cx0 = Math.random() * S
      const cy0 = Math.random() * S
      const bladeCount = 3 + Math.floor(Math.random() * 5)
      const baseAngle = -Math.PI / 2 + (Math.random() - 0.5) * 0.4

      for (let b = 0; b < bladeCount; b++) {
        const angle = baseAngle + (Math.random() - 0.5) * 1.2
        const len = 4 + Math.random() * 10
        const g = 70 + Math.random() * 70
        const r = 25 + Math.random() * 40
        ctx.strokeStyle = `rgba(${r}, ${g}, ${Math.floor(r * 0.55)}, 0.55)`
        ctx.lineWidth = 0.5 + Math.random() * 1.2
        ctx.beginPath()
        ctx.moveTo(cx0 + (Math.random() - 0.5) * 3, cy0 + (Math.random() - 0.5) * 2)
        const tipX = cx0 + Math.cos(angle) * len
        const tipY = cy0 + Math.sin(angle) * len
        // Slight curve via quadratic bezier for natural blade shape
        const cpX = cx0 + Math.cos(angle) * len * 0.6 + (Math.random() - 0.5) * 3
        const cpY = cy0 + Math.sin(angle) * len * 0.6
        ctx.quadraticCurveTo(cpX, cpY, tipX, tipY)
        ctx.stroke()

        // Bright tip highlight (sunlit blade tips)
        if (Math.random() < 0.3) {
          ctx.strokeStyle = `rgba(${100 + Math.random() * 40}, ${150 + Math.random() * 30}, ${60 + Math.random() * 20}, 0.3)`
          ctx.lineWidth = 0.3
          ctx.beginPath()
          ctx.moveTo(tipX - Math.cos(angle) * 2, tipY - Math.sin(angle) * 2)
          ctx.lineTo(tipX, tipY)
          ctx.stroke()
        }
      }
    }

    // Layer 3: scattered individual fine blades for density
    for (let i = 0; i < 3000; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const len = 2 + Math.random() * 5
      const angle = -Math.PI / 2 + (Math.random() - 0.5) * 1.0
      const g = 75 + Math.random() * 65
      const r = 28 + Math.random() * 35
      ctx.strokeStyle = `rgba(${r}, ${g}, ${Math.floor(r * 0.5)}, 0.4)`
      ctx.lineWidth = 0.3 + Math.random() * 0.7
      ctx.beginPath()
      ctx.moveTo(x, y)
      ctx.lineTo(x + Math.cos(angle) * len, y + Math.sin(angle) * len)
      ctx.stroke()
    }

    // Layer 4: bright speckles (dew/light catch)
    for (let i = 0; i < 800; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      ctx.fillStyle = `rgba(${90 + Math.random() * 50}, ${130 + Math.random() * 50}, ${50 + Math.random() * 30}, 0.12)`
      ctx.fillRect(x, y, 1, 1)
    }

    // Layer 5: radial edge darkening (vignette)
    const cx = S / 2
    const cy = S / 2
    const maxR = S / 2
    const edgeData = ctx.getImageData(0, 0, S, S)
    const ed = edgeData.data
    for (let y = 0; y < S; y++) {
      for (let x = 0; x < S; x++) {
        const dx = x - cx
        const dy = y - cy
        const dist = Math.sqrt(dx * dx + dy * dy) / maxR
        if (dist > 0.55) {
          const t = Math.min((dist - 0.55) / 0.45, 1.0)
          const darken = 1.0 - t * 0.4
          const idx = (y * S + x) * 4
          ed[idx] = Math.floor(ed[idx] * darken)
          ed[idx + 1] = Math.floor(ed[idx + 1] * darken)
          ed[idx + 2] = Math.floor(ed[idx + 2] * darken)
        }
      }
    }
    // Write vignette-modified pixels directly to texture (skip canvas round-trip).
    // `mipmaps: true` is explicit — with LINEAR_MIPMAP_LINEAR min filter the
    // sampler requires a complete mip chain, otherwise WebGL returns black.
    const texture = new pc.Texture(device, {
      width: S,
      height: S,
      format: pc.PIXELFORMAT_RGBA8,
      mipmaps: true,
      addressU: pc.ADDRESS_REPEAT,
      addressV: pc.ADDRESS_REPEAT,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      anisotropy: 4,
    })

    const pixels = texture.lock()
    pixels.set(ed)
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
    if (this.pngImage) {
      this.pngImage.onload = null
      this.pngImage.onerror = null
      // Letting the browser reclaim the cached decode is enough; no .src reset
      // needed since we just drop our reference.
      this.pngImage = null
    }
    if (this.pngTexture) {
      this.pngTexture.destroy()
      this.pngTexture = null
    }
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
