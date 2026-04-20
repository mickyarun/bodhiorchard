// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * FinishArch — procedural finish-line gantry with a FINISH banner.
 *
 * Two white cylindrical posts flanking the road at the finish line, a
 * dark horizontal beam across the top, and a canvas-textured banner
 * hanging from the beam with the word "FINISH" painted in large type.
 *
 * Self-contained geometry + materials + canvas texture. Disposed via
 * destroy() — the entity cascade tears down the sub-entities, and we
 * null/destroy the banner texture and material we created ourselves.
 */
import * as pc from 'playcanvas'
import { disposeEntity, safeDestroyMaterial, safeDestroyTexture } from './dispose'

// Larger & more dramatic — the finish gantry is the single most
// recognizable silhouette at a distance, so it carries the scene.
const POST_HEIGHT_M = 6.5
const POST_RADIUS_M = 0.22
const BEAM_DEPTH_M = 0.45
const BEAM_HEIGHT_M = 6.0  // y-position of beam centre

/** Small pennants strung across the top of the beam — stadium vibe. */
const PENNANT_COUNT = 14
const PENNANT_HEIGHT_M = 0.45
const PENNANT_Y_M = BEAM_HEIGHT_M + 0.30

const BANNER_WIDTH_RATIO = 0.9   // banner width as fraction of track width
const BANNER_HEIGHT_M = 1.6
const BANNER_Y_M = BEAM_HEIGHT_M - 1.3  // hang below the beam

const BANNER_CANVAS_W = 1024
const BANNER_CANVAS_H = 256

const POST_COLOR = { r: 0.98, g: 0.98, b: 0.98 }
const BEAM_COLOR = { r: 0.12, g: 0.12, b: 0.14 }
const PENNANT_COLORS: Array<[number, number, number]> = [
  [0.95, 0.30, 0.30],
  [0.95, 0.80, 0.30],
  [0.40, 0.85, 0.55],
  [0.30, 0.60, 0.95],
]

/**
 * Euler angles that stand a horizontal `pc.Plane` up vertically and rotate
 * it so its front face points toward the approaching runners (-X side).
 *
 * FIX HISTORY: the old implementation pre-mirrored the canvas + used a
 * negative X scale hoping the two flips would cancel. They didn't — the
 * plane's visible face (under CULLFACE_NONE) depended on camera angle
 * and viewers consistently saw "HSINIF". New approach: two opposing
 * planes, each with plain text, CULLFACE_BACK. The front-facing plane
 * is readable to approaching racers, the back-facing one to the
 * spectator camera once racers have crossed.
 */
const BANNER_FRONT_EULER_X_DEG = -90
const BANNER_FRONT_EULER_Y_DEG = 90
const BANNER_BACK_EULER_Y_DEG = -90   // mirror image for the post-finish side

export interface FinishArchOptions {
  /** Road width in metres. Arch posts flare slightly outside this. */
  trackWidthM: number
  /** World X at which the finish arch stands — usually the race's `distanceM`. */
  xAtFinish: number
}

export class FinishArch {
  private root: pc.Entity | null = null
  private materials: pc.StandardMaterial[] = []
  private bannerTexture: pc.Texture | null = null

  build(parent: pc.Entity, device: pc.GraphicsDevice, opts: FinishArchOptions): void {
    const root = new pc.Entity('FinishArch')
    root.setLocalPosition(opts.xAtFinish, 0, 0)
    parent.addChild(root)
    this.root = root

    const postMat = this.makeMaterial(POST_COLOR.r, POST_COLOR.g, POST_COLOR.b)
    const beamMat = this.makeMaterial(BEAM_COLOR.r, BEAM_COLOR.g, BEAM_COLOR.b)

    // Two posts flanking the road — a little outside the painted edge so
    // the arch visually frames the full track.
    const postZ = opts.trackWidthM / 2 + 0.3
    for (const zSide of [-postZ, postZ]) {
      const post = new pc.Entity('ArchPost')
      post.addComponent('render', { type: 'cylinder' })
      post.render!.meshInstances[0].material = postMat
      post.setLocalScale(POST_RADIUS_M * 2, POST_HEIGHT_M, POST_RADIUS_M * 2)
      post.setLocalPosition(0, POST_HEIGHT_M / 2, zSide)
      root.addChild(post)
    }

    // Horizontal beam — a simple box spanning between the posts with slight overhang.
    const beam = new pc.Entity('ArchBeam')
    beam.addComponent('render', { type: 'box' })
    beam.render!.meshInstances[0].material = beamMat
    beam.setLocalScale(BEAM_DEPTH_M, BEAM_DEPTH_M, postZ * 2 + POST_RADIUS_M * 4)
    beam.setLocalPosition(0, BEAM_HEIGHT_M, 0)
    root.addChild(beam)

    // Two back-to-back banners. Each is one-sided (CULLFACE_BACK), drawing
    // "FINISH" normally on the canvas, with a rotation that makes the
    // front-face point at the relevant viewer. No UV mirror trick — the
    // cancelled-flip approach used to intermittently show "HSINIF".
    const texture = this.makeFinishTexture(device)
    this.bannerTexture = texture
    const mat = this.makeBannerMaterial(texture)
    root.addChild(this.buildBannerPlane(mat, opts.trackWidthM * BANNER_WIDTH_RATIO, BANNER_FRONT_EULER_Y_DEG, 'FinishBanner_Front'))
    root.addChild(this.buildBannerPlane(mat, opts.trackWidthM * BANNER_WIDTH_RATIO, BANNER_BACK_EULER_Y_DEG, 'FinishBanner_Back'))

    // Pennants across the top of the beam — simple coloured triangles
    // (approximated with thin rotated planes) spaced evenly. Adds a
    // stadium/fair vibe without an image.
    this.addPennants(root, opts.trackWidthM)
  }

  /**
   * Row of coloured pennants hanging from the top beam. Each pennant is
   * a small plane tinted with an unlit colour so it reads crisp against
   * the sky at all times of day.
   */
  private addPennants(root: pc.Entity, trackWidthM: number): void {
    const bannerLen = trackWidthM * BANNER_WIDTH_RATIO + 1.5
    const step = bannerLen / PENNANT_COUNT
    const startZ = -bannerLen / 2 + step / 2
    for (let i = 0; i < PENNANT_COUNT; i++) {
      const [r, g, b] = PENNANT_COLORS[i % PENNANT_COLORS.length]
      const mat = new pc.StandardMaterial()
      mat.diffuse = new pc.Color(r, g, b)
      mat.useLighting = true
      mat.cull = pc.CULLFACE_NONE
      mat.gloss = 0.15
      mat.update()
      this.materials.push(mat)

      const pennant = new pc.Entity('Pennant')
      pennant.addComponent('render', { type: 'plane' })
      pennant.render!.meshInstances[0].material = mat
      // Stand upright and face -X (toward approaching racers). The pennant
      // dangles downward from the beam; simple rectangle approximation.
      pennant.setLocalEulerAngles(-90, 90, 0)
      pennant.setLocalScale(0.28, 1, PENNANT_HEIGHT_M)
      pennant.setLocalPosition(0, PENNANT_Y_M, startZ + i * step)
      root.addChild(pennant)
    }
  }

  destroy(): void {
    disposeEntity(this.root)
    this.root = null

    safeDestroyTexture(this.bannerTexture)
    this.bannerTexture = null

    for (const mat of this.materials) safeDestroyMaterial(mat)
    this.materials = []
  }

  private makeMaterial(r: number, g: number, b: number): pc.StandardMaterial {
    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(r, g, b)
    mat.metalness = 0
    mat.gloss = 0.15
    mat.update()
    this.materials.push(mat)
    return mat
  }

  /** Shared material for both banner planes — both sides reference the
   *  same texture + colour, so we only pay for one set of GPU uploads. */
  private makeBannerMaterial(texture: pc.Texture): pc.StandardMaterial {
    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(0, 0, 0)
    mat.emissiveMap = texture
    mat.emissive = new pc.Color(1, 1, 1)
    mat.opacityMap = texture
    mat.opacityMapChannel = 'a'
    mat.blendType = pc.BLEND_NORMAL
    mat.depthWrite = false
    // One-sided: each banner plane is one face of the pair, so back-face
    // culling hides the side that would otherwise show mirrored text.
    mat.cull = pc.CULLFACE_BACK
    mat.update()
    this.materials.push(mat)
    return mat
  }

  /**
   * One banner plane. `yEulerDeg` selects which side the plane faces:
   *   +90 → normal points -X (visible to approaching runners)
   *   -90 → normal points +X (visible from behind the arch)
   *
   * Positive scale + text drawn normally on the canvas = text reads
   * left-to-right from the visible side.
   */
  private buildBannerPlane(
    mat: pc.StandardMaterial,
    widthM: number,
    yEulerDeg: number,
    name: string,
  ): pc.Entity {
    const entity = new pc.Entity(name)
    entity.addComponent('render', { type: 'plane' })
    entity.render!.meshInstances[0].material = mat
    entity.setLocalEulerAngles(BANNER_FRONT_EULER_X_DEG, yEulerDeg, 0)
    entity.setLocalScale(widthM, 1, BANNER_HEIGHT_M)
    entity.setLocalPosition(0, BANNER_Y_M, 0)
    return entity
  }

  private makeFinishTexture(device: pc.GraphicsDevice): pc.Texture {
    const canvas = document.createElement('canvas')
    canvas.width = BANNER_CANVAS_W
    canvas.height = BANNER_CANVAS_H
    const ctx = canvas.getContext('2d')!

    // Red banner background (classic racing finish).
    ctx.fillStyle = '#d22222'
    ctx.fillRect(0, 0, BANNER_CANVAS_W, BANNER_CANVAS_H)

    // Black & white checker border — top and bottom strips.
    const stripH = 24
    const squareW = 32
    for (let row = 0; row < 2; row++) {
      const y = row === 0 ? 0 : BANNER_CANVAS_H - stripH
      for (let x = 0; x < BANNER_CANVAS_W; x += squareW) {
        const col = Math.floor(x / squareW)
        ctx.fillStyle = (col + row) % 2 === 0 ? '#ffffff' : '#111111'
        ctx.fillRect(x, y, squareW, stripH)
      }
    }

    // FINISH text drawn normally — orientation is handled by the plane
    // rotation in buildBannerPlane(), no canvas-side flipping required.
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 140px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.lineWidth = 6
    ctx.strokeStyle = '#111111'
    const textX = BANNER_CANVAS_W / 2
    const textY = BANNER_CANVAS_H / 2
    ctx.strokeText('FINISH', textX, textY)
    ctx.fillText('FINISH', textX, textY)

    const texture = new pc.Texture(device, {
      width: BANNER_CANVAS_W, height: BANNER_CANVAS_H,
      minFilter: pc.FILTER_LINEAR, magFilter: pc.FILTER_LINEAR,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE, addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      mipmaps: false,
    })
    texture.setSource(canvas)
    return texture
  }

}
