/**
 * GraphLabelSystem — canvas-rendered billboard text labels for graph nodes.
 *
 * Creates a 2D canvas with text, uploads it as a texture, and applies it
 * to a plane entity that faces the camera each frame (billboard behavior).
 *
 * Labels are registered with the PlayCanvas app's update loop for
 * billboard rotation (lookAt camera each frame).
 */
import * as pc from 'playcanvas'

const LABEL_CANVAS_WIDTH = 1024
const LABEL_CANVAS_HEIGHT = 128
const FONT_SIZE = 72
const FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'

export interface LabelHandle {
  entity: pc.Entity
  texture: pc.Texture
  material: pc.StandardMaterial
}

export class GraphLabelSystem {
  private labels: LabelHandle[] = []
  private cameraEntity: pc.Entity | null = null

  setCameraEntity(camera: pc.Entity): void {
    this.cameraEntity = camera
  }

  /** Create a billboard label attached as a child of `parent`. */
  createLabel(
    app: pc.AppBase,
    text: string,
    parent: pc.Entity,
    yOffset: number,
    scale = 4,
  ): LabelHandle {
    // 1. Render text to a canvas
    const canvas = document.createElement('canvas')
    canvas.width = LABEL_CANVAS_WIDTH
    canvas.height = LABEL_CANVAS_HEIGHT
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.font = `bold ${FONT_SIZE}px ${FONT_FAMILY}`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'

    // Text shadow for readability
    ctx.shadowColor = 'rgba(0,0,0,0.7)'
    ctx.shadowBlur = 6
    ctx.shadowOffsetX = 1
    ctx.shadowOffsetY = 1
    ctx.fillStyle = '#FFFFFF'
    ctx.fillText(text, canvas.width / 2, canvas.height / 2)

    // 2. Upload as texture
    const texture = new pc.Texture(app.graphicsDevice, {
      width: canvas.width,
      height: canvas.height,
      format: pc.PIXELFORMAT_RGBA8,
      mipmaps: true,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE,
      addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      minFilter: pc.FILTER_LINEAR_MIPMAP_LINEAR,
      magFilter: pc.FILTER_LINEAR,
      anisotropy: 8,
    })
    texture.setSource(canvas)

    // 3. Create material with texture
    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(0, 0, 0, 0)
    mat.emissiveMap = texture
    mat.emissive = new pc.Color(1, 1, 1)
    mat.opacityMap = texture
    mat.opacityMapChannel = 'a'
    mat.blendType = pc.BLEND_NORMAL
    mat.depthWrite = false
    mat.cull = pc.CULLFACE_NONE
    mat.update()

    // 4. Create plane entity
    const entity = new pc.Entity(`Label_${text}`)
    entity.addComponent('render', { type: 'plane' })
    entity.render!.meshInstances[0].material = mat

    // Scale: preserve aspect ratio
    const aspect = LABEL_CANVAS_WIDTH / LABEL_CANVAS_HEIGHT
    entity.setLocalScale(scale * aspect, scale, 1)
    entity.setLocalPosition(0, yOffset, 0)

    parent.addChild(entity)

    const handle: LabelHandle = { entity, texture, material: mat }
    this.labels.push(handle)
    return handle
  }

  /** Update all labels to face the camera (call each frame). */
  updateBillboards(): void {
    if (!this.cameraEntity) return
    const camPos = this.cameraEntity.getPosition()

    for (const label of this.labels) {
      if (!label.entity.enabled) continue
      // lookAt makes entity's -Z face the camera
      label.entity.lookAt(camPos)
      // Plane default is XZ (faces +Y). Rotate to face camera and flip text right-reading.
      label.entity.rotateLocal(90, 180, 0)
    }
  }

  /** Remove a specific label. */
  removeLabel(handle: LabelHandle): void {
    handle.entity.destroy()
    handle.material.destroy()
    handle.texture.destroy()
    const idx = this.labels.indexOf(handle)
    if (idx !== -1) this.labels.splice(idx, 1)
  }

  /** Destroy all labels. */
  destroy(): void {
    for (const label of this.labels) {
      label.entity.destroy()
      label.material.destroy()
      label.texture.destroy()
    }
    this.labels = []
  }
}
