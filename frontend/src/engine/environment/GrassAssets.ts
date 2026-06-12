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
 * GrassAssets — procedural textures and meshes for the grass carpet.
 *
 * The carpet look depends on the blade art: many THIN, slightly curved,
 * overlapping blades whose roots sit at the ground color so each tuft
 * grows out of the terrain instead of reading as a clump stuck on top.
 * Per-blade hue jitter keeps the field from looking stamped.
 *
 * Flower tufts share the crossed-quad mesh: grass-green stems with a
 * simple painterly blossom (petal ellipses around a center dot) — far
 * softer than the scaled-up GLB tulips they replace.
 */
import * as pc from 'playcanvas'
import { Theme, type Rgb255 } from '../rendering/Theme'

const BLADE_TEX_W = 192
const BLADE_TEX_H = 128
const FLOWER_TEX = 128

function lerpChannel(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t)
}

function uploadCanvas(device: pc.GraphicsDevice, canvas: HTMLCanvasElement): pc.Texture {
  const ctx = canvas.getContext('2d')!
  const texture = new pc.Texture(device, {
    width: canvas.width,
    height: canvas.height,
    format: pc.PIXELFORMAT_RGBA8,
    mipmaps: true,
    addressU: pc.ADDRESS_CLAMP_TO_EDGE,
    addressV: pc.ADDRESS_CLAMP_TO_EDGE,
    minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
    magFilter: pc.FILTER_LINEAR,
    anisotropy: 4,
  })
  const pixels = texture.lock()
  pixels.set(ctx.getImageData(0, 0, canvas.width, canvas.height).data)
  texture.unlock()
  return texture
}

/** Dense painterly blade sheet: ~20 thin curved blades, root→tip gradient
 *  in the ground's hue family, per-blade jitter. */
export function buildBladeTexture(device: pc.GraphicsDevice): pc.Texture {
  const canvas = document.createElement('canvas')
  canvas.width = BLADE_TEX_W
  canvas.height = BLADE_TEX_H
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, BLADE_TEX_W, BLADE_TEX_H)

  const root = Theme.GRASS_BLADES.root
  const tip = Theme.GRASS_BLADES.tip
  const bladeCount = 20

  for (let b = 0; b < bladeCount; b++) {
    const cx = ((b + 0.5) / bladeCount) * BLADE_TEX_W + (Math.random() - 0.5) * 7
    const h = BLADE_TEX_H * (0.5 + Math.random() * 0.48)
    const w = 3.5 + Math.random() * 4
    const lean = (Math.random() - 0.5) * BLADE_TEX_W * 0.16
    const jitter = (Math.random() - 0.5) * 22

    // Each blade is painted in 6 stacked segments so the gradient follows
    // the blade's own curve (a single linear gradient ignores the lean).
    const segments = 6
    for (let s = 0; s < segments; s++) {
      const t0 = s / segments
      const t1 = (s + 1) / segments
      // Quadratic lean: offset grows with height²
      const x0 = cx + lean * t0 * t0
      const x1 = cx + lean * t1 * t1
      const y0 = BLADE_TEX_H - h * t0
      const y1 = BLADE_TEX_H - h * t1
      const w0 = w * (1 - t0 * 0.85)
      const w1 = w * (1 - t1 * 0.85)
      const tMid = (t0 + t1) / 2
      const r = lerpChannel(root[0], tip[0], tMid) + jitter * 0.4
      const g = lerpChannel(root[1], tip[1], tMid) + jitter
      const bl = lerpChannel(root[2], tip[2], tMid) + jitter * 0.3
      ctx.fillStyle = `rgb(${r}, ${g}, ${bl})`
      ctx.beginPath()
      ctx.moveTo(x0 - w0, y0)
      ctx.lineTo(x0 + w0, y0)
      ctx.lineTo(x1 + w1, y1)
      ctx.lineTo(x1 - w1, y1)
      ctx.closePath()
      ctx.fill()
    }
  }

  return uploadCanvas(device, canvas)
}

/** Flower tuft sheet: three thin stems topped with painterly blossoms. */
export function buildFlowerTexture(device: pc.GraphicsDevice, petal: Rgb255): pc.Texture {
  const S = FLOWER_TEX
  const canvas = document.createElement('canvas')
  canvas.width = S
  canvas.height = S
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, S, S)

  const stem = Theme.FLOWERS.stem
  const stems = [
    { x: S * 0.3, h: S * 0.62, lean: -S * 0.06 },
    { x: S * 0.52, h: S * 0.82, lean: S * 0.02 },
    { x: S * 0.74, h: S * 0.56, lean: S * 0.08 },
  ]

  for (const st of stems) {
    // Stem
    ctx.strokeStyle = `rgb(${stem[0]}, ${stem[1]}, ${stem[2]})`
    ctx.lineWidth = 2.5
    ctx.beginPath()
    ctx.moveTo(st.x, S)
    ctx.quadraticCurveTo(st.x + st.lean * 0.4, S - st.h * 0.6, st.x + st.lean, S - st.h)
    ctx.stroke()

    // Blossom: 6 petal ellipses around a warm center
    const bx = st.x + st.lean
    const by = S - st.h
    const petalR = 5.5 + Math.random() * 1.5
    ctx.fillStyle = `rgb(${petal[0]}, ${petal[1]}, ${petal[2]})`
    for (let p = 0; p < 6; p++) {
      const a = (p / 6) * Math.PI * 2
      ctx.beginPath()
      ctx.ellipse(
        bx + Math.cos(a) * petalR * 0.9,
        by + Math.sin(a) * petalR * 0.9,
        petalR * 0.62, petalR * 0.42, a, 0, Math.PI * 2,
      )
      ctx.fill()
    }
    ctx.fillStyle = 'rgb(244, 196, 84)'
    ctx.beginPath()
    ctx.arc(bx, by, petalR * 0.4, 0, Math.PI * 2)
    ctx.fill()
  }

  return uploadCanvas(device, canvas)
}

/** Three quads crossed at 60° around Y, base at y=0, tip at `height`.
 *  Up-biased normals so the lighting reads as ground cover. */
export function buildCrossQuadMesh(
  device: pc.GraphicsDevice, width: number, height: number,
): pc.Mesh {
  const positions: number[] = []
  const normals: number[] = []
  const uvs: number[] = []
  const indices: number[] = []
  const hw = width / 2

  for (let q = 0; q < 3; q++) {
    const a = (q * Math.PI) / 3
    const dx = Math.cos(a) * hw
    const dz = Math.sin(a) * hw
    const base = q * 4
    positions.push(
      -dx, 0, -dz,   dx, 0, dz,
       dx, height, dz,   -dx, height, -dz,
    )
    for (let v = 0; v < 4; v++) normals.push(0, 1, 0)
    uvs.push(0, 0, 1, 0, 1, 1, 0, 1)
    indices.push(base, base + 1, base + 2, base, base + 2, base + 3)
  }

  const geometry = new pc.Geometry()
  geometry.positions = positions
  geometry.normals = normals
  geometry.uvs = uvs
  geometry.indices = indices
  return pc.Mesh.fromGeometry(device, geometry)
}

/** Alpha-tested, two-sided foliage material over a generated sheet. */
export function buildFoliageMaterial(texture: pc.Texture): pc.StandardMaterial {
  const mat = new pc.StandardMaterial()
  mat.diffuseMap = texture
  mat.opacityMap = texture
  mat.opacityMapChannel = 'a'
  mat.alphaTest = 0.45
  mat.cull = pc.CULLFACE_NONE
  mat.twoSidedLighting = true
  mat.metalness = 0
  mat.gloss = 0.1
  mat.update()
  return mat
}
