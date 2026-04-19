// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * ChalkboardRenderer — wall-mounted multi-line sign using Canvas2D → texture.
 *
 * Sibling to LabelRenderer but:
 *   - Multi-line (title + list of items) instead of a single line
 *   - NOT registered as a billboard → keeps whatever rotation the caller sets
 *   - Fixed aspect ratio (driven by caller-provided width / height)
 *   - Canvas content is NOT pre-mirrored: without the billboard transform,
 *     the plane is read from its natural +Y face so text is right-reading
 *     when the entity is rotated into place
 *
 * Visual style is chalkboard-on-wood: dark slate background, a rounded pill
 * housing the title at the top, and the item list rendered in warm chalk
 * cream below. Colours are sampled from the café reference.
 *
 * Callers position and rotate the returned entity (e.g. `setLocalEulerAngles(90, 0, 0)`
 * mounts it vertically on a +Z-facing wall).
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'

export interface ChalkboardOptions {
  /** Header text shown in the title pill. */
  title: string
  /** Line items shown below the title. */
  items: string[]
  /** World-space plane width (x axis). */
  width: number
  /** World-space plane height (z axis — plane is XZ, caller rotates). */
  height: number
  /** Texture pixel height. Canvas width derives from the aspect ratio. */
  texHeight?: number
}

const DEFAULT_TEX_HEIGHT = 512

// Palette — sampled from the Gemini café reference.
const BG_CHALKBOARD = '#1f1813'        // deep near-black slate
const BG_TITLE_PILL = '#8b6943'        // medium warm wood
const COLOR_TITLE_TEXT = '#fff4d6'     // warm cream
const COLOR_ITEM_TEXT = '#f5e6c8'      // chalk cream
const COLOR_BORDER = 'rgba(255, 244, 214, 0.25)'

export class ChalkboardRenderer {
  /** Create a chalkboard plane entity at local origin with normal +Y. */
  static create(appRef: Application, opts: ChalkboardOptions): pc.Entity {
    const texH = opts.texHeight ?? DEFAULT_TEX_HEIGHT
    const texW = Math.round(texH * (opts.width / opts.height))

    const texture = ChalkboardRenderer.renderToTexture(
      appRef.app.graphicsDevice, texW, texH, opts,
    )

    const entity = new pc.Entity(`Chalkboard_${opts.title}`)
    entity.addComponent('render', { type: 'plane' })
    entity.setLocalScale(opts.width, 1, opts.height)
    const mi = entity.render!.meshInstances[0]
    mi.material = ChalkboardRenderer.createMaterial(texture)
    // Draw after standard world geometry so the menu wins overlap sorts
    // even with depth test disabled.
    mi.drawOrder = 1000
    return entity
  }

  /** Release GPU resources. Does NOT destroy the entity — caller handles that. */
  static cleanup(entity: pc.Entity): void {
    if (!entity.render?.meshInstances?.length) return
    for (const mi of entity.render.meshInstances) {
      const mat = mi.material as pc.StandardMaterial
      if (mat.diffuseMap) mat.diffuseMap.destroy()
      mat.destroy()
    }
  }

  // ─── Private helpers ─────────────────────────────────

  private static createMaterial(texture: pc.Texture): pc.StandardMaterial {
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

  private static renderToTexture(
    device: pc.GraphicsDevice,
    w: number,
    h: number,
    opts: ChalkboardOptions,
  ): pc.Texture {
    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')!

    // ─── Slate background ──────────────────────────
    ctx.fillStyle = BG_CHALKBOARD
    ctx.fillRect(0, 0, w, h)

    // Subtle inner border (chalk-dust frame)
    ctx.strokeStyle = COLOR_BORDER
    ctx.lineWidth = 2
    ctx.strokeRect(8, 8, w - 16, h - 16)

    // ─── Title pill (rounded rect with warm wood fill) ────
    const titleFontSize = Math.round(h * 0.11)
    const pillPadX = Math.round(w * 0.05)
    const pillPadY = Math.round(h * 0.02)
    const pillTop = Math.round(h * 0.06)

    ctx.font = `bold ${titleFontSize}px "Segoe UI", Arial, sans-serif`
    const titleWidth = ctx.measureText(opts.title).width
    const pillW = titleWidth + pillPadX * 2
    const pillH = titleFontSize + pillPadY * 2
    const pillX = (w - pillW) / 2

    ctx.fillStyle = BG_TITLE_PILL
    ChalkboardRenderer.roundRect(ctx, pillX, pillTop, pillW, pillH, 16)
    ctx.fill()

    ctx.fillStyle = COLOR_TITLE_TEXT
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(opts.title, w / 2, pillTop + pillH / 2)

    // ─── Item list (chalk cream text) ─────────────────
    const itemFontSize = Math.round(h * 0.095)
    ctx.font = `600 ${itemFontSize}px "Segoe UI", Arial, sans-serif`
    ctx.fillStyle = COLOR_ITEM_TEXT
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'

    const itemsTop = pillTop + pillH + Math.round(h * 0.08)
    const itemsBottom = h - Math.round(h * 0.08)
    const availableH = itemsBottom - itemsTop
    const lineH = opts.items.length > 1
      ? Math.min(availableH / opts.items.length, itemFontSize * 1.6)
      : itemFontSize * 1.6

    const startY = itemsTop + (availableH - lineH * opts.items.length) / 2 + lineH / 2
    opts.items.forEach((item, i) => {
      ctx.fillText(item, w / 2, startY + i * lineH)
    })

    // ─── Upload to GPU texture ──────────────────────
    const texture = new pc.Texture(device, {
      width: w,
      height: h,
      format: pc.PIXELFORMAT_RGBA8,
      minFilter: pc.FILTER_LINEAR,
      magFilter: pc.FILTER_LINEAR,
    })

    const pixels = texture.lock()
    pixels.set(ctx.getImageData(0, 0, w, h).data)
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
