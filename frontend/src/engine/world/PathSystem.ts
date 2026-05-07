// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * PathSystem — Tiered path network connecting world zones.
 *
 * Two visual tiers, driven by {@link PathRoute.kind}:
 *   - primary   — hub ↔ activity zones. Wider (3.0u), sand-colored, with
 *                 stepping stones on top, gently curved (quadratic Bezier).
 *   - secondary — activity ↔ habitation zones. Narrower (2.0u), dirt-tinted,
 *                 straight, no stones. Reads as "branch from main path"
 *                 instead of competing with primary for attention.
 *
 * Curved paths are rendered as a chain of plane segments sampled along a
 * quadratic Bezier; stepping stones follow the same sampling. Straight
 * paths collapse to a single segment.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { randRange } from '../utils/MathUtils'
import { END_TRIM, evalRouteAt, type PathRoute } from '@shared/world/paths'

// Layout primitives (`PathRoute`, `PathKind`, `END_TRIM`, `evalRouteAt`,
// `buildRoutes`) live in `shared/world/paths.ts` — consumers should import
// from there directly rather than via this renderer.

const PATH_ASSET = 'assets/garden/path_stone.glb'
const STONE_SPACING = 1.8
const STONE_SCALE = 1.5
const SAND_TEX_SIZE = 128

/** Visual width of a primary (hub↔activity) path strip. Exported so
 *  consumers (e.g. GrassDressing's wear halos) size correctly. */
export const PRIMARY_WIDTH = 3.0
/** Visual width of a secondary (hub↔habitation) path strip. */
export const SECONDARY_WIDTH = 2.0
/** Number of segments used to approximate a curved route. 16 is smooth
 *  enough at this scale without explosive draw-call cost. */
export const BEZIER_SEGMENTS = 16

export class PathSystem {
  private root: pc.Entity | null = null
  private sandTexture: pc.Texture | null = null
  private primaryMat: pc.StandardMaterial | null = null
  private secondaryMat: pc.StandardMaterial | null = null

  async build(
    app: Application,
    loader: AssetLoader,
    routes: PathRoute[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('PathSystem')

    this.sandTexture = this.createSandTexture(app.app.graphicsDevice)
    this.primaryMat = this.createStripMaterial(new pc.Color(1, 1, 1))
    // Dirt tint: warmer and darker than sand — reads as worn-in secondary path.
    this.secondaryMat = this.createStripMaterial(new pc.Color(0.65, 0.5, 0.38))

    const stoneAsset = await loader.load(PATH_ASSET)

    for (const route of routes) {
      const kind = route.kind ?? 'primary'
      const width = kind === 'primary' ? PRIMARY_WIDTH : SECONDARY_WIDTH
      const material = kind === 'primary' ? this.primaryMat : this.secondaryMat
      if (!material) continue

      const points = this.sampleRoute(route)
      if (points.length < 2) continue

      // Skip extremely short paths (e.g., overlapping zones) — would just
      // flicker as a tiny strip.
      const totalDist = this.pathLength(points)
      if (totalDist < 2) continue

      this.drawStrip(points, width, material)

      if (kind === 'primary') {
        this.placeSteppingStones(points, totalDist, stoneAsset, loader)
      }
    }

    app.root.addChild(this.root)
    return this.root
  }

  /**
   * Sample a route into a polyline. Straight routes yield 2 points;
   * curved routes yield BEZIER_SEGMENTS+1 points evenly spaced in t.
   * Both ends are trimmed inward by END_TRIM so the strip stops before
   * crashing into the zone disc at each terminus.
   */
  private sampleRoute(route: PathRoute): Array<{ x: number; z: number }> {
    const isCurved = route.controlX !== undefined && route.controlZ !== undefined
    const segments = isCurved ? BEZIER_SEGMENTS : 1
    const tStart = END_TRIM
    const tEnd = 1 - END_TRIM
    const points: Array<{ x: number; z: number }> = []
    for (let i = 0; i <= segments; i++) {
      const t = tStart + (tEnd - tStart) * (i / segments)
      points.push(evalRouteAt(route, t))
    }
    return points
  }

  private pathLength(points: Array<{ x: number; z: number }>): number {
    let total = 0
    for (let i = 0; i < points.length - 1; i++) {
      const dx = points[i + 1].x - points[i].x
      const dz = points[i + 1].z - points[i].z
      total += Math.sqrt(dx * dx + dz * dz)
    }
    return total
  }

  /** Render the polyline as a chain of plane segments. */
  private drawStrip(
    points: Array<{ x: number; z: number }>,
    width: number,
    material: pc.StandardMaterial,
  ): void {
    for (let i = 0; i < points.length - 1; i++) {
      const p0 = points[i]
      const p1 = points[i + 1]
      const dx = p1.x - p0.x
      const dz = p1.z - p0.z
      const length = Math.sqrt(dx * dx + dz * dz)
      if (length < 0.01) continue
      const midX = (p0.x + p1.x) / 2
      const midZ = (p0.z + p1.z) / 2
      const angle = Math.atan2(dx, dz) * (180 / Math.PI)

      // Overlap segments by 5% so we don't get seams where alpha-faded
      // texture edges meet; the combined strip reads as continuous.
      const segLength = length * 1.05

      const strip = new pc.Entity('PathSegment')
      strip.addComponent('render', { type: 'plane' })
      strip.setLocalScale(width, 1, segLength)
      strip.setPosition(midX, 0.015, midZ)
      strip.setLocalEulerAngles(0, angle, 0)
      strip.render!.meshInstances[0].material = material
      this.root!.addChild(strip)
    }
  }

  /**
   * Distribute stepping stones along a sampled polyline at STONE_SPACING
   * arc-length intervals. Each stone is oriented along the local tangent
   * of the segment it falls in.
   */
  private placeSteppingStones(
    points: Array<{ x: number; z: number }>,
    totalDist: number,
    asset: pc.Asset,
    loader: AssetLoader,
  ): void {
    const count = Math.floor(totalDist / STONE_SPACING)
    if (count < 2) return

    // Pre-compute per-segment distances for fast arc-length → segment lookup.
    const segDists: number[] = []
    for (let i = 0; i < points.length - 1; i++) {
      const dx = points[i + 1].x - points[i].x
      const dz = points[i + 1].z - points[i].z
      segDists.push(Math.sqrt(dx * dx + dz * dz))
    }

    for (let k = 1; k < count; k++) {
      const targetD = (k / count) * totalDist
      let acc = 0
      for (let i = 0; i < segDists.length; i++) {
        if (acc + segDists[i] >= targetD) {
          const tLocal = (targetD - acc) / segDists[i]
          const p0 = points[i]
          const p1 = points[i + 1]
          const sx = p0.x + (p1.x - p0.x) * tLocal + randRange(-0.15, 0.15)
          const sz = p0.z + (p1.z - p0.z) * tLocal + randRange(-0.15, 0.15)
          const pathAngle = Math.atan2(p1.x - p0.x, p1.z - p0.z) * (180 / Math.PI)

          const stone = loader.instance(asset)
          stone.setPosition(sx, 0.02, sz)
          stone.setLocalEulerAngles(0, pathAngle + randRange(-10, 10), 0)
          const s = STONE_SCALE + randRange(-0.2, 0.2)
          stone.setLocalScale(s, s, s)
          this.root!.addChild(stone)
          break
        }
        acc += segDists[i]
      }
    }
  }

  /** Shared strip material factory — both tiers reuse the sand alpha mask
   *  so edges fade softly; differ only in diffuse tint. */
  private createStripMaterial(tint: pc.Color): pc.StandardMaterial {
    const mat = new pc.StandardMaterial()
    mat.diffuseMap = this.sandTexture
    mat.diffuse = tint
    mat.metalness = 0
    mat.gloss = 0.06
    mat.opacityMap = this.sandTexture
    mat.alphaTest = 0.01
    mat.blendType = pc.BLEND_NORMAL
    mat.depthWrite = false
    mat.cull = pc.CULLFACE_NONE
    mat.update()
    return mat
  }

  /** Procedural sand texture with soft alpha edges. */
  private createSandTexture(device: pc.GraphicsDevice): pc.Texture {
    const S = SAND_TEX_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = S
    canvas.height = S
    const ctx = canvas.getContext('2d')!

    ctx.fillStyle = 'rgb(195, 175, 135)'
    ctx.fillRect(0, 0, S, S)

    for (let i = 0; i < 40; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const r = 5 + Math.random() * 20
      const dr = Math.floor((Math.random() - 0.5) * 30)
      ctx.beginPath()
      ctx.arc(x, y, r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(${195 + dr}, ${175 + dr * 0.8}, ${135 + dr * 0.6}, 0.3)`
      ctx.fill()
    }

    for (let i = 0; i < 300; i++) {
      const x = Math.random() * S
      const y = Math.random() * S
      const dr = Math.floor((Math.random() - 0.5) * 40)
      ctx.fillStyle = `rgba(${195 + dr}, ${175 + dr * 0.8}, ${135 + dr * 0.6}, 0.2)`
      ctx.fillRect(x, y, 1 + Math.random(), 1 + Math.random())
    }

    const imageData = ctx.getImageData(0, 0, S, S)
    const data = imageData.data
    for (let y = 0; y < S; y++) {
      for (let x = 0; x < S; x++) {
        const edgeDist = Math.min(x, S - 1 - x) / (S / 2)
        let alpha: number
        if (edgeDist < 0.3) {
          const t = edgeDist / 0.3
          alpha = t * t * (3 - 2 * t)
        } else {
          alpha = 1.0
        }
        const idx = (y * S + x) * 4
        data[idx + 3] = Math.floor(data[idx + 3] * alpha)
      }
    }

    const texture = new pc.Texture(device, {
      width: S,
      height: S,
      format: pc.PIXELFORMAT_RGBA8,
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
    if (this.sandTexture) {
      this.sandTexture.destroy()
      this.sandTexture = null
    }
    if (this.primaryMat) {
      this.primaryMat.destroy()
      this.primaryMat = null
    }
    if (this.secondaryMat) {
      this.secondaryMat.destroy()
      this.secondaryMat = null
    }
  }
}
