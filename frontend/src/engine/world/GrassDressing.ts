// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * GrassDressing — Path-wear halos beneath primary paths.
 *
 * Lays wider, darker dirt tint strips UNDER each primary path, simulating
 * foot traffic wear outside the main stepping path so the transition from
 * grass to sand feels "trodden" not "stapled."
 *
 * Layering: grass(y=0) → wear(y=0.008) → path(y=0.015) → zone(y=0.02).
 *
 * (Macro color overlay was removed after z-fight issues with the 600×600
 * ground plane — any full-map transparent layer at near-coplanar y either
 * z-fights, or needs depthTest=false which causes foreground geometry to
 * appear transparent. The right long-term fix for global grass tinting is
 * to bake it into GroundSystem's grass material rather than a separate
 * plane; deferring until that work is scoped.)
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { evalRouteAt, END_TRIM, type PathRoute } from '@shared/world/paths'
import { PRIMARY_WIDTH, BEZIER_SEGMENTS } from './PathSystem'

/** Wear strip sits between ground and path strip. */
const WEAR_Y = 0.008
/** Extra width beyond PRIMARY_WIDTH so wear halo extends past path edges. */
const WEAR_WIDTH_ADD = 2.5
const WEAR_TEX_SIZE = 128

export class GrassDressing {
  private root: pc.Entity | null = null
  private textures: pc.Texture[] = []
  private materials: pc.StandardMaterial[] = []
  private wearMaterial: pc.StandardMaterial | null = null

  build(app: Application, routes: readonly PathRoute[]): void {
    this.root = new pc.Entity('GrassDressing')
    app.root.addChild(this.root)

    this.wearMaterial = this.createWearMaterial(app.app.graphicsDevice)
    this.addPathWear(routes)
  }

  /**
   * Lay darker dirt strips under each primary path — a "worn grass" halo
   * that softens the grass↔sand transition and signals "people walk
   * here." Uses the same Bezier sampling as PathSystem so the wear
   * follows curves exactly. Secondary paths get no wear (they're
   * meant to read as narrower side-tracks, not main thoroughfares).
   */
  private addPathWear(routes: readonly PathRoute[]): void {
    for (const route of routes) {
      if ((route.kind ?? 'primary') !== 'primary') continue

      const pts = this.sampleRoute(route)
      for (let i = 0; i < pts.length - 1; i++) {
        const p0 = pts[i]
        const p1 = pts[i + 1]
        const dx = p1.x - p0.x
        const dz = p1.z - p0.z
        const length = Math.sqrt(dx * dx + dz * dz)
        if (length < 0.01) continue
        const midX = (p0.x + p1.x) / 2
        const midZ = (p0.z + p1.z) / 2
        const angle = Math.atan2(dx, dz) * (180 / Math.PI)

        const strip = new pc.Entity('PathWear')
        strip.addComponent('render', { type: 'plane' })
        // 5% length overlap to hide seams at segment joins (same trick as PathSystem).
        strip.setLocalScale(PRIMARY_WIDTH + WEAR_WIDTH_ADD, 1, length * 1.05)
        strip.setPosition(midX, WEAR_Y, midZ)
        strip.setLocalEulerAngles(0, angle, 0)
        strip.render!.meshInstances[0].material = this.wearMaterial!
        strip.render!.castShadows = false
        this.root!.addChild(strip)
      }
    }
  }

  private sampleRoute(route: PathRoute): Array<{ x: number; z: number }> {
    const segments = route.curve === 'bezier' ? BEZIER_SEGMENTS : 1
    const tStart = END_TRIM
    const tEnd = 1 - END_TRIM
    const pts: Array<{ x: number; z: number }> = []
    for (let i = 0; i <= segments; i++) {
      const t = tStart + (tEnd - tStart) * (i / segments)
      pts.push(evalRouteAt(route, t))
    }
    return pts
  }

  private createWearMaterial(device: pc.GraphicsDevice): pc.StandardMaterial {
    const tex = this.createWearTexture(device)
    const mat = new pc.StandardMaterial()
    mat.diffuseMap = tex
    // Warm brown tint — not fully desaturated dirt, so the wear reads as
    // "packed earth" rather than "dead patch."
    mat.diffuse = new pc.Color(0.62, 0.52, 0.38)
    mat.opacityMap = tex
    mat.alphaTest = 0.01
    mat.blendType = pc.BLEND_NORMAL
    mat.depthWrite = false
    mat.metalness = 0
    mat.gloss = 0.03
    mat.cull = pc.CULLFACE_NONE
    mat.update()
    this.textures.push(tex)
    this.materials.push(mat)
    return mat
  }

  /**
   * Stripe texture with broad soft fade on short edges (path width axis).
   * Alpha at the path centerline peaks at ~0.6 so the grass underneath
   * is still visible — we're tinting, not covering.
   */
  private createWearTexture(device: pc.GraphicsDevice): pc.Texture {
    const S = WEAR_TEX_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = S
    canvas.height = S
    const ctx = canvas.getContext('2d')!

    ctx.fillStyle = 'rgb(95, 80, 55)'
    ctx.fillRect(0, 0, S, S)

    // Noise patches for organic variation
    for (let i = 0; i < 35; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const r = 4 + Math.random() * 18
      const dr = Math.floor((Math.random() - 0.5) * 25)
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${95 + dr}, ${80 + dr * 0.8}, ${55 + dr * 0.6}, 0.4)`
      ctx.fill()
    }

    // Broad alpha fade across short edges (path-width axis = X texel axis).
    // Unlike the sand path's cliff-edge, wear fades more gradually so grass
    // bleeds through → "soft halo" not "second path."
    const imageData = ctx.getImageData(0, 0, S, S)
    const data = imageData.data
    for (let y = 0; y < S; y++) {
      for (let x = 0; x < S; x++) {
        const edgeDist = Math.min(x, S - 1 - x) / (S / 2)
        // Smoothstep from edge (alpha=0) to center (alpha=0.6).
        const t = Math.min(edgeDist / 0.9, 1)
        const alpha = t * t * (3 - 2 * t) * 0.6
        const idx = (y * S + x) * 4
        data[idx + 3] = Math.floor(alpha * 255)
      }
    }

    const texture = new pc.Texture(device, {
      width: S,
      height: S,
      format: pc.PIXELFORMAT_RGBA8,
      mipmaps: true,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_REPEAT,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      anisotropy: 2,
    })

    const pixels = texture.lock()
    pixels.set(data)
    texture.unlock()
    return texture
  }

  destroy(): void {
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
    for (const tex of this.textures) tex.destroy()
    for (const mat of this.materials) mat.destroy()
    this.textures = []
    this.materials = []
    this.wearMaterial = null
  }
}
