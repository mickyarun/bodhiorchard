/**
 * GroundBuilder — procedural dirt patch with grass ring.
 *
 * No external assets. Creates a textured plane from a procedural
 * canvas-to-texture radial gradient (dirt center → grass edge).
 */
import * as pc from 'playcanvas'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import type { TransitionManager } from './TransitionManager'
import { randRange } from '../utils/MathUtils'

const TEXTURE_SIZE = 256
const Z_FIGHT_OFFSET = 0.001

export class GroundBuilder {
  private app: pc.AppBase
  private materials: MaterialFactory
  private groundEntity: pc.Entity | null = null
  private groundTexture: pc.Texture | null = null
  private propsRoot: pc.Entity | null = null
  private currentRadius = 0
  private propsPlaced = false

  constructor(app: pc.AppBase, materials: MaterialFactory) {
    this.app = app
    this.materials = materials
  }

  build(parent: pc.Entity, radius: number): void {
    this.currentRadius = radius
    this.groundTexture = this.createGroundTexture()

    const mat = new pc.StandardMaterial()
    mat.diffuseMap = this.groundTexture
    mat.metalness = 0
    mat.gloss = 0.1
    mat.update()

    this.groundEntity = new pc.Entity('Ground')
    this.groundEntity.addComponent('render', { type: 'plane' })
    this.groundEntity.render!.meshInstances[0].material = mat
    this.groundEntity.setLocalScale(radius * 2, 1, radius * 2)
    this.groundEntity.setPosition(0, Z_FIGHT_OFFSET, 0)
    parent.addChild(this.groundEntity)

    this.propsRoot = new pc.Entity('GroundProps')
    parent.addChild(this.propsRoot)
  }

  setRadius(radius: number, transitions: TransitionManager): void {
    if (!this.groundEntity) return
    const from = this.currentRadius
    this.currentRadius = radius
    transitions.add({
      from: from * 2, to: radius * 2, duration: 1.5,
      applyFn: (v) => this.groundEntity?.setLocalScale(v, 1, v),
    })
  }

  /** Add procedural grass/rock props (small cylinders + spheres). */
  async addProps(groundRadius: number): Promise<void> {
    if (this.propsPlaced || !this.propsRoot) return
    this.propsPlaced = true

    const grassMat = this.materials.getColor('grass_prop', 0.2, 0.5, 0.15, {
      metalness: 0, gloss: 0.2,
    })
    const rockMat = this.materials.getColor('rock_prop', 0.5, 0.48, 0.44, {
      metalness: 0.1, gloss: 0.3,
    })

    // Scatter grass tufts around perimeter
    const grassCount = Math.round(groundRadius * 3)
    for (let i = 0; i < grassCount; i++) {
      const angle = (i / grassCount) * Math.PI * 2 + randRange(-0.3, 0.3)
      const dist = groundRadius * randRange(0.55, 0.85)
      const entity = new pc.Entity('Grass')
      entity.addComponent('render', { type: 'cone' })
      entity.render!.meshInstances[0].material = grassMat
      entity.setPosition(Math.cos(angle) * dist, 0.04, Math.sin(angle) * dist)
      entity.setLocalScale(0.04, 0.08, 0.04)
      entity.setEulerAngles(randRange(-5, 5), randRange(0, 360), randRange(-5, 5))
      this.propsRoot.addChild(entity)
    }

    // Scatter small rocks
    const rockCount = Math.max(2, Math.round(groundRadius))
    for (let i = 0; i < rockCount; i++) {
      const angle = randRange(0, Math.PI * 2)
      const dist = groundRadius * randRange(0.3, 0.65)
      const entity = new pc.Entity('Rock')
      entity.addComponent('render', { type: 'sphere' })
      entity.render!.meshInstances[0].material = rockMat
      const s = randRange(0.03, 0.06)
      entity.setPosition(Math.cos(angle) * dist, s * 0.3, Math.sin(angle) * dist)
      entity.setLocalScale(s * 1.3, s * 0.7, s)
      this.propsRoot.addChild(entity)
    }
  }

  private createGroundTexture(): pc.Texture {
    const size = TEXTURE_SIZE
    const canvas = document.createElement('canvas')
    canvas.width = size
    canvas.height = size
    const ctx = canvas.getContext('2d')!

    const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    gradient.addColorStop(0, '#6B4423')
    gradient.addColorStop(0.3, '#8B6914')
    gradient.addColorStop(0.6, '#5A7D2B')
    gradient.addColorStop(0.8, '#4A8B2F')
    gradient.addColorStop(1.0, '#3D7A28')
    ctx.fillStyle = gradient
    ctx.fillRect(0, 0, size, size)

    // Organic noise
    const imgData = ctx.getImageData(0, 0, size, size)
    for (let i = 0; i < imgData.data.length; i += 4) {
      const noise = (Math.random() - 0.5) * 15
      imgData.data[i] = Math.max(0, Math.min(255, imgData.data[i] + noise))
      imgData.data[i + 1] = Math.max(0, Math.min(255, imgData.data[i + 1] + noise))
      imgData.data[i + 2] = Math.max(0, Math.min(255, imgData.data[i + 2] + noise))
    }
    ctx.putImageData(imgData, 0, 0)

    const texture = new pc.Texture(this.app.graphicsDevice, {
      width: size, height: size,
      format: pc.PIXELFORMAT_RGBA8,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
    })
    const source = texture.lock()
    const pixels = ctx.getImageData(0, 0, size, size).data
    for (let i = 0; i < pixels.length; i++) source[i] = pixels[i]
    texture.unlock()
    return texture
  }

  destroy(): void {
    this.propsRoot?.destroy(); this.propsRoot = null
    this.groundEntity?.destroy(); this.groundEntity = null
    this.groundTexture?.destroy(); this.groundTexture = null
    this.propsPlaced = false
  }
}
