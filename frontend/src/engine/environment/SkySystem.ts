/**
 * SkySystem — Sky dome using a StandardMaterial with a generated gradient texture.
 *
 * Instead of custom shaders (which crash in PCV2 multi-pass rendering),
 * we generate a sky gradient texture via Canvas2D and apply it as the
 * emissiveMap on a StandardMaterial. The emissive channel renders the sky
 * without needing directional lighting, while still participating in
 * the PBR pipeline's render passes (shadow, depth, etc.).
 *
 * The visible sky dome is separate from the IBL cubemap (used for reflections).
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { MaterialFactory } from '../rendering/MaterialFactory'

const SKY_TEX_WIDTH = 256
const SKY_TEX_HEIGHT = 128

export class SkySystem {
  private entity: pc.Entity | null = null
  private material: pc.StandardMaterial | null = null
  private texture: pc.Texture | null = null

  build(app: Application, _materials: MaterialFactory): pc.Entity {
    // Inverted sphere as sky dome — must fit within camera farClip
    this.entity = new pc.Entity('SkyDome')
    this.entity.addComponent('render', { type: 'sphere' })
    this.entity.setLocalScale(1000, 1000, 1000)

    // Generate sky gradient texture
    this.texture = this.createSkyTexture(app.app.graphicsDevice)

    // StandardMaterial with emissive sky — participates in all render passes
    this.material = new pc.StandardMaterial()
    this.material.diffuse = new pc.Color(0, 0, 0)
    this.material.emissiveMap = this.texture
    this.material.emissive = new pc.Color(1, 1, 1)
    this.material.cull = pc.CULLFACE_FRONT // render inside of sphere
    this.material.depthWrite = false // sky is always behind everything
    this.material.update()

    const meshInstance = this.entity.render!.meshInstances[0]
    meshInstance.material = this.material

    app.root.addChild(this.entity)
    return this.entity
  }

  /** Generate a gradient texture: horizon → zenith + below-horizon ground fade. */
  private createSkyTexture(device: pc.GraphicsDevice): pc.Texture {
    const canvas = document.createElement('canvas')
    canvas.width = SKY_TEX_WIDTH
    canvas.height = SKY_TEX_HEIGHT
    const ctx = canvas.getContext('2d')!

    // Sky gradient (bottom = horizon, top = zenith)
    const gradient = ctx.createLinearGradient(0, canvas.height, 0, 0)
    gradient.addColorStop(0.0, 'rgb(75, 120, 65)')     // below horizon — muted green
    gradient.addColorStop(0.30, 'rgb(85, 130, 70)')    // ground fade
    gradient.addColorStop(0.44, 'rgb(195, 215, 240)')  // near horizon — warm haze
    gradient.addColorStop(0.50, 'rgb(180, 210, 245)')  // horizon line
    gradient.addColorStop(0.65, 'rgb(135, 185, 240)')  // lower sky
    gradient.addColorStop(0.80, 'rgb(100, 160, 235)')  // mid sky
    gradient.addColorStop(1.0, 'rgb(70, 130, 220)')    // zenith — deeper blue

    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Sun disc — bright visible sun in the sky
    const sunX = canvas.width * 0.65
    const sunY = canvas.height * 0.38 // higher in sky for visibility

    // Outer halo glow (warm orange)
    const halo = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, 60)
    halo.addColorStop(0, 'rgba(255, 240, 200, 0.6)')
    halo.addColorStop(0.4, 'rgba(255, 220, 160, 0.2)')
    halo.addColorStop(1, 'rgba(255, 220, 160, 0)')
    ctx.fillStyle = halo
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Inner glow (bright warm)
    const innerGlow = ctx.createRadialGradient(sunX, sunY, 0, sunX, sunY, 20)
    innerGlow.addColorStop(0, 'rgba(255, 255, 240, 1.0)')
    innerGlow.addColorStop(0.4, 'rgba(255, 250, 220, 0.9)')
    innerGlow.addColorStop(0.7, 'rgba(255, 240, 190, 0.4)')
    innerGlow.addColorStop(1, 'rgba(255, 235, 180, 0)')
    ctx.fillStyle = innerGlow
    ctx.fillRect(0, 0, canvas.width, canvas.height)

    // Bright sun core disc
    ctx.beginPath()
    ctx.arc(sunX, sunY, 6, 0, Math.PI * 2)
    ctx.fillStyle = 'rgba(255, 255, 250, 1.0)'
    ctx.fill()

    const texture = new pc.Texture(device, {
      width: canvas.width,
      height: canvas.height,
      format: pc.PIXELFORMAT_RGBA8,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      minFilter: pc.FILTER_LINEAR,
      magFilter: pc.FILTER_LINEAR,
    })

    const pixels = texture.lock()
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
    pixels.set(imageData.data)
    texture.unlock()

    return texture
  }

  update(_dt: number): void {
    // Static sky for now — Phase 4 time system can update texture
  }

  destroy(): void {
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
