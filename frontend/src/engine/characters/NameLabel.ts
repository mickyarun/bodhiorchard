/**
 * NameLabel — Shared billboard name label for character entities.
 *
 * Creates a canvas-textured plane positioned above the character's head.
 * Used by both KayKit and legacy Kenney character factories.
 */
import * as pc from 'playcanvas'

const LABEL_WIDTH = 1.2
const LABEL_CANVAS_W = 256
const LABEL_CANVAS_H = 64

/**
 * Create a billboard name label entity.
 *
 * @param name - Display name text
 * @param device - PlayCanvas graphics device for texture creation
 * @param height - Y position above the character's feet (world units)
 */
export function createNameLabel(
  name: string,
  device: pc.GraphicsDevice,
  height: number,
): pc.Entity {
  const canvas = document.createElement('canvas')
  canvas.width = LABEL_CANVAS_W
  canvas.height = LABEL_CANVAS_H
  const ctx = canvas.getContext('2d')!

  ctx.clearRect(0, 0, LABEL_CANVAS_W, LABEL_CANVAS_H)

  // Semi-transparent background pill
  const padding = 8
  const r = 12
  const left = padding, top = 4
  const w = LABEL_CANVAS_W - padding * 2, h = LABEL_CANVAS_H - 8
  ctx.fillStyle = 'rgba(0, 0, 0, 0.5)'
  ctx.beginPath()
  ctx.moveTo(left + r, top)
  ctx.arcTo(left + w, top, left + w, top + h, r)
  ctx.arcTo(left + w, top + h, left, top + h, r)
  ctx.arcTo(left, top + h, left, top, r)
  ctx.arcTo(left, top, left + w, top, r)
  ctx.closePath()
  ctx.fill()

  // White text
  ctx.fillStyle = '#ffffff'
  ctx.font = 'bold 28px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(name, LABEL_CANVAS_W / 2, LABEL_CANVAS_H / 2, LABEL_CANVAS_W - padding * 2)

  const texture = new pc.Texture(device, {
    width: LABEL_CANVAS_W, height: LABEL_CANVAS_H,
    minFilter: pc.FILTER_LINEAR, magFilter: pc.FILTER_LINEAR,
    addressU: pc.ADDRESS_CLAMP_TO_EDGE, addressV: pc.ADDRESS_CLAMP_TO_EDGE,
    mipmaps: false,
  })
  texture.setSource(canvas)

  // Ad-hoc material — each label has a unique emissive texture (per-member name),
  // so MaterialFactory caching does not apply here.
  const material = new pc.StandardMaterial()
  material.diffuse = new pc.Color(0, 0, 0)
  material.emissiveMap = texture
  material.emissive = new pc.Color(1, 1, 1)
  material.opacityMap = texture
  material.opacityMapChannel = 'a'
  material.blendType = pc.BLEND_NORMAL
  material.depthWrite = false
  material.cull = pc.CULLFACE_NONE
  material.update()

  const entity = new pc.Entity('NameLabel')
  entity.addComponent('render', { type: 'plane' })
  entity.render!.meshInstances[0].material = material
  entity.setLocalPosition(0, height, 0)
  entity.setLocalScale(-LABEL_WIDTH, 1, LABEL_WIDTH * (LABEL_CANVAS_H / LABEL_CANVAS_W))
  entity.setLocalEulerAngles(90, 0, 0)
  entity.tags.add('billboard')

  return entity
}
