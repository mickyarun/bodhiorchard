/**
 * LabelRenderer — Billboard text labels using canvas-to-texture.
 *
 * Creates a plane entity with text rendered via Canvas2D, registered as a
 * billboard so Application's frame loop keeps it facing the camera.
 * Same pattern as ZoneSign but designed for floating labels above entities.
 *
 * The entity is created at the local origin — callers position it
 * (e.g. as a child of a tree, character, or building).
 *
 * Canvas width is dynamically sized to fit the text — no truncation.
 *
 * Mirror fix: The billboard rotation (lookAt + rotateLocal(90,0,0)) views
 * the texture from behind the plane's natural face. Canvas content is drawn
 * horizontally flipped so it reads correctly after the billboard transform.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'

/** Canvas texture height (fixed). Width is computed per-label to fit text. */
const TEX_H = 96
const PAD_X = 24
const PAD_Y = 12

/** World-space height of the label plane (width scales with text). */
const WORLD_H = 0.6

export interface LabelOptions {
  fontSize?: number
  textColor?: string
  bgColor?: string | null
  borderRadius?: number
}

const LABEL_DEFAULTS: Required<LabelOptions> = {
  fontSize: 36,
  textColor: '#FFFFFF',
  bgColor: 'rgba(30,30,30,0.7)',
  borderRadius: 16,
}

export class LabelRenderer {
  /**
   * Create a billboard label entity at local origin.
   * Registered with app.registerBillboard() to auto-face the camera.
   * Caller is responsible for positioning and parenting the returned entity.
   */
  static create(
    appRef: Application,
    text: string,
    options: LabelOptions = {},
  ): pc.Entity {
    const opts = { ...LABEL_DEFAULTS, ...options }

    // Measure text to determine canvas width before creating the texture
    const texW = LabelRenderer.measureCanvasWidth(text, opts.fontSize)
    const worldW = WORLD_H * (texW / TEX_H)

    const entity = new pc.Entity(`Label_${text}`)
    entity.addComponent('render', { type: 'plane' })
    entity.setLocalScale(worldW, 1, WORLD_H)

    const texture = LabelRenderer.renderTextToTexture(appRef.app.graphicsDevice, text, texW, opts)
    entity.render!.meshInstances[0].material = LabelRenderer.createLabelMaterial(texture)

    appRef.registerBillboard(entity)
    return entity
  }

  /**
   * Unregister billboard and release GPU resources (texture + material).
   * Does NOT destroy the entity — caller or parent.destroy() handles that.
   */
  static cleanup(appRef: Application, entity: pc.Entity): void {
    appRef.unregisterBillboard(entity)
    if (!entity.render?.meshInstances?.length) return
    for (const mi of entity.render.meshInstances) {
      const mat = mi.material as pc.StandardMaterial
      if (mat.diffuseMap) mat.diffuseMap.destroy()
      mat.destroy()
    }
  }

  // ─── Private helpers ─────────────────────────────

  /** Measure the canvas pixel width needed to fit text + padding. */
  private static measureCanvasWidth(text: string, fontSize: number): number {
    const canvas = document.createElement('canvas')
    canvas.width = 1
    canvas.height = 1
    const ctx = canvas.getContext('2d')!
    ctx.font = `bold ${fontSize}px "Segoe UI", Arial, sans-serif`
    const textWidth = ctx.measureText(text).width
    return Math.ceil(textWidth + PAD_X * 2)
  }

  /**
   * Intentional MaterialFactory bypass: each label has a unique texture
   * (different text), so materials can't be shared/cached. MaterialFactory
   * is designed for color-based materials, not per-instance texture maps.
   * Callers MUST call cleanup() before destroying the label entity.
   */
  private static createLabelMaterial(texture: pc.Texture): pc.StandardMaterial {
    const mat = new pc.StandardMaterial()
    mat.diffuseMap = texture
    mat.emissiveMap = texture
    mat.emissive = new pc.Color(1, 1, 1)
    mat.opacityMap = texture
    mat.opacityMapChannel = 'a'
    mat.blendType = pc.BLEND_NORMAL
    mat.depthWrite = false
    mat.cull = pc.CULLFACE_NONE
    mat.update()
    return mat
  }

  private static renderTextToTexture(
    device: pc.GraphicsDevice,
    text: string,
    texW: number,
    opts: Required<LabelOptions>,
  ): pc.Texture {
    const canvas = document.createElement('canvas')
    canvas.width = texW
    canvas.height = TEX_H
    const ctx = canvas.getContext('2d')!

    ctx.clearRect(0, 0, texW, TEX_H)

    // Flip horizontally — billboard rotation views the texture from behind,
    // so pre-mirroring the canvas makes text read correctly in 3D.
    ctx.translate(texW, 0)
    ctx.scale(-1, 1)

    // Background pill
    ctx.font = `bold ${opts.fontSize}px "Segoe UI", Arial, sans-serif`
    const textWidth = ctx.measureText(text).width
    const pillW = textWidth + PAD_X * 2
    const pillH = opts.fontSize + PAD_Y * 2
    const pillX = (texW - pillW) / 2
    const pillY = (TEX_H - pillH) / 2

    if (opts.bgColor) {
      ctx.fillStyle = opts.bgColor
      LabelRenderer.roundRect(ctx, pillX, pillY, pillW, pillH, opts.borderRadius)
      ctx.fill()
    }

    ctx.fillStyle = opts.textColor
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(text, texW / 2, TEX_H / 2)

    const texture = new pc.Texture(device, {
      width: texW,
      height: TEX_H,
      format: pc.PIXELFORMAT_RGBA8,
      minFilter: pc.FILTER_LINEAR,
      magFilter: pc.FILTER_LINEAR,
    })

    const pixels = texture.lock()
    pixels.set(ctx.getImageData(0, 0, texW, TEX_H).data)
    texture.unlock()

    return texture
  }

  private static roundRect(
    ctx: CanvasRenderingContext2D,
    x: number, y: number, w: number, h: number, r: number,
  ): void {
    ctx.beginPath()
    ctx.moveTo(x + r, y)
    ctx.lineTo(x + w - r, y)
    ctx.quadraticCurveTo(x + w, y, x + w, y + r)
    ctx.lineTo(x + w, y + h - r)
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h)
    ctx.lineTo(x + r, y + h)
    ctx.quadraticCurveTo(x, y + h, x, y + h - r)
    ctx.lineTo(x, y + r)
    ctx.quadraticCurveTo(x, y, x + r, y)
    ctx.closePath()
  }
}
