/**
 * LevelBadge — small billboard badge showing developer level above their name.
 *
 * Renders a compact canvas texture with level icon + number.
 * Positioned above the NameLabel in the character entity hierarchy.
 * Tagged 'billboard' for per-frame camera-facing rotation.
 */
import * as pc from 'playcanvas'

const BADGE_CANVAS_W = 128
const BADGE_CANVAS_H = 48
const BADGE_WIDTH = 0.6

const LEVEL_ICONS: Record<string, string> = {
  seedling: '🌱',
  sprout: '🌿',
  sapling: '🌲',
  tree: '🌳',
  ancient_oak: '🏔️',
}

/**
 * Create a level badge entity.
 *
 * @param level - Current level number
 * @param levelName - Level name (seedling, sprout, etc.)
 * @param device - PlayCanvas graphics device
 * @param height - Y position above character feet
 */
export function createLevelBadge(
  level: number,
  levelName: string,
  device: pc.GraphicsDevice,
  height: number,
): pc.Entity {
  const canvas = document.createElement('canvas')
  canvas.width = BADGE_CANVAS_W
  canvas.height = BADGE_CANVAS_H
  const ctx = canvas.getContext('2d')!

  ctx.clearRect(0, 0, BADGE_CANVAS_W, BADGE_CANVAS_H)

  // Background pill
  const pad = 4, r = 8
  ctx.fillStyle = 'rgba(40, 80, 40, 0.7)'
  ctx.beginPath()
  ctx.moveTo(pad + r, pad)
  ctx.arcTo(BADGE_CANVAS_W - pad, pad, BADGE_CANVAS_W - pad, BADGE_CANVAS_H - pad, r)
  ctx.arcTo(BADGE_CANVAS_W - pad, BADGE_CANVAS_H - pad, pad, BADGE_CANVAS_H - pad, r)
  ctx.arcTo(pad, BADGE_CANVAS_H - pad, pad, pad, r)
  ctx.arcTo(pad, pad, BADGE_CANVAS_W - pad, pad, r)
  ctx.closePath()
  ctx.fill()

  // Level icon + text
  const icon = LEVEL_ICONS[levelName] || '⭐'
  ctx.font = '20px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#ffffff'
  ctx.fillText(`${icon} Lv.${level}`, BADGE_CANVAS_W / 2, BADGE_CANVAS_H / 2)

  // Create texture
  const texture = new pc.Texture(device, {
    width: BADGE_CANVAS_W, height: BADGE_CANVAS_H,
    minFilter: pc.FILTER_LINEAR, magFilter: pc.FILTER_LINEAR,
    addressU: pc.ADDRESS_CLAMP_TO_EDGE, addressV: pc.ADDRESS_CLAMP_TO_EDGE,
    mipmaps: false,
  })
  texture.setSource(canvas)

  // Ad-hoc emissive material — same pattern as NameLabel (unique texture per badge)
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

  const entity = new pc.Entity('LevelBadge')
  entity.addComponent('render', { type: 'plane' })
  entity.render!.meshInstances[0].material = material
  entity.setLocalPosition(0, height, 0)
  entity.setLocalScale(-BADGE_WIDTH, 1, BADGE_WIDTH * (BADGE_CANVAS_H / BADGE_CANVAS_W))
  entity.setLocalEulerAngles(90, 0, 0)
  entity.tags.add('billboard')

  return entity
}
