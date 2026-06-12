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
 * AmbientParticles — warm pollen motes drifting over the garden.
 *
 * One GPU particle system: ~80 soft dots on a wide box emitter at canopy
 * height, slow upward drift with gentle sideways wander. Pure "the air is
 * alive" dressing — negligible cost (single draw call, GPU-simulated).
 *
 * Built once per engine life (parented to the engine root, NOT the garden
 * root) so incremental scene updates never respawn the motes; destroyed
 * with the engine.
 */
import * as pc from 'playcanvas'

const PARTICLE_COUNT = 80
const LIFETIME_S = 12
const EMITTER_HALF_X = 55
const EMITTER_HALF_Y = 4
const EMITTER_HALF_Z = 55
const EMITTER_CENTER_Y = 5
const DOT_TEX_SIZE = 16
/** Warm pollen white — matches the Theme sun family. */
const MOTE_COLOR = new pc.Color(1.0, 0.95, 0.82)

export class AmbientParticles {
  private entity: pc.Entity | null = null
  private texture: pc.Texture | null = null

  build(app: pc.AppBase, parent: pc.Entity): void {
    this.texture = this.createDotTexture(app.graphicsDevice)

    this.entity = new pc.Entity('AmbientPollen')
    this.entity.addComponent('particlesystem', {
      numParticles: PARTICLE_COUNT,
      lifetime: LIFETIME_S,
      rate: LIFETIME_S / PARTICLE_COUNT,
      rate2: LIFETIME_S / PARTICLE_COUNT,
      emitterShape: pc.EMITTERSHAPE_BOX,
      emitterExtents: new pc.Vec3(EMITTER_HALF_X * 2, EMITTER_HALF_Y * 2, EMITTER_HALF_Z * 2),
      colorMap: this.texture,
      blendType: pc.BLEND_ADDITIVE,
      depthWrite: false,
      lighting: false,
      loop: true,
      preWarm: true,
      // Slow rise with a hint of sideways wander
      localVelocityGraph: new pc.CurveSet([
        [0, -0.15, 1, 0.15],   // x: gentle wander
        [0, 0.12, 1, 0.3],     // y: slow upward drift
        [0, -0.15, 1, 0.15],   // z: gentle wander
      ]),
      // Fade in → hold → fade out
      alphaGraph: new pc.Curve([0, 0, 0.2, 0.55, 0.8, 0.55, 1, 0]),
      scaleGraph: new pc.Curve([0, 0.06, 0.5, 0.09, 1, 0.06]),
      colorGraph: new pc.CurveSet([
        [0, MOTE_COLOR.r], [0, MOTE_COLOR.g], [0, MOTE_COLOR.b],
      ]),
    })
    this.entity.setPosition(0, EMITTER_CENTER_Y, 0)
    parent.addChild(this.entity)
  }

  /** Soft radial dot — generated, no asset dependency. */
  private createDotTexture(device: pc.GraphicsDevice): pc.Texture {
    const S = DOT_TEX_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = S
    canvas.height = S
    const ctx = canvas.getContext('2d')!
    const grad = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2)
    grad.addColorStop(0, 'rgba(255, 255, 255, 1)')
    grad.addColorStop(0.5, 'rgba(255, 255, 255, 0.5)')
    grad.addColorStop(1, 'rgba(255, 255, 255, 0)')
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, S, S)

    const texture = new pc.Texture(device, {
      width: S,
      height: S,
      format: pc.PIXELFORMAT_RGBA8,
      mipmaps: true,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
    })
    const pixels = texture.lock()
    pixels.set(ctx.getImageData(0, 0, S, S).data)
    texture.unlock()
    return texture
  }

  destroy(): void {
    this.entity?.destroy()
    this.entity = null
    this.texture?.destroy()
    this.texture = null
  }
}
