// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * AgentLabel — floating two-line billboard label for agent characters.
 *
 * Top line: agent skill name (bold)
 * Bottom line: current action text
 *
 * Uses canvas-textured plane with emissive material (self-lit, PBR-safe).
 * Billboard rotation handled by Application's per-frame billboard loop.
 */
import * as pc from 'playcanvas'

const CANVAS_W = 512
const CANVAS_H = 96
const LABEL_WIDTH = 1.8
const LABEL_Y = 1.6   // height above agent feet

export class AgentLabel {
  private entity: pc.Entity | null = null
  private texture: pc.Texture | null = null
  private material: pc.StandardMaterial | null = null
  private device: pc.GraphicsDevice
  private canvas: HTMLCanvasElement | null = null

  constructor(device: pc.GraphicsDevice) {
    this.device = device
  }

  /** Create the label entity. Call once, then update text via setText(). */
  create(name: string, action: string): pc.Entity {
    const canvas = this.renderCanvas(name, action)
    this.texture = new pc.Texture(this.device, {
      width: CANVAS_W, height: CANVAS_H,
      minFilter: pc.FILTER_LINEAR, magFilter: pc.FILTER_LINEAR,
      addressU: pc.ADDRESS_CLAMP_TO_EDGE, addressV: pc.ADDRESS_CLAMP_TO_EDGE,
      mipmaps: false,
    })
    this.texture.setSource(canvas)

    this.material = new pc.StandardMaterial()
    this.material.diffuse = new pc.Color(0, 0, 0)
    this.material.emissiveMap = this.texture
    this.material.emissive = new pc.Color(1, 1, 1)
    this.material.opacityMap = this.texture
    this.material.opacityMapChannel = 'a'
    this.material.blendType = pc.BLEND_NORMAL
    this.material.depthWrite = false
    this.material.cull = pc.CULLFACE_NONE
    this.material.update()

    this.entity = new pc.Entity('AgentLabel')
    this.entity.addComponent('render', { type: 'plane' })
    this.entity.render!.meshInstances[0].material = this.material
    this.entity.setLocalPosition(0, LABEL_Y, 0)
    this.entity.setLocalScale(-LABEL_WIDTH, 1, LABEL_WIDTH * (CANVAS_H / CANVAS_W))
    this.entity.setLocalEulerAngles(90, 0, 0)
    this.entity.tags.add('billboard')

    return this.entity
  }

  private bgColor = 'rgba(30, 60, 120, 0.75)'
  private currentName = ''
  private currentAction = ''

  /** Update the label text (re-renders the canvas texture). */
  setText(name: string, action: string): void {
    if (!this.texture) return
    this.currentName = name
    this.currentAction = action
    const canvas = this.renderCanvas(name, action)
    this.texture.setSource(canvas)
  }

  /** Reposition the label height (call after measuring robot AABB). */
  setHeight(y: number): void {
    this.entity?.setLocalPosition(0, y, 0)
  }

  /** Tint the background pill color and re-render. */
  setColor(r: number, g: number, b: number): void {
    this.bgColor = `rgba(${Math.round(r * 255)}, ${Math.round(g * 255)}, ${Math.round(b * 255)}, 0.75)`
    if (this.currentName) this.setText(this.currentName, this.currentAction)
  }

  destroy(): void {
    this.entity?.destroy()
    this.entity = null
    this.material?.destroy()
    this.material = null
    this.texture?.destroy()
    this.texture = null
  }

  private renderCanvas(name: string, action: string): HTMLCanvasElement {
    if (!this.canvas) {
      this.canvas = document.createElement('canvas')
      this.canvas.width = CANVAS_W
      this.canvas.height = CANVAS_H
    }
    const canvas = this.canvas
    const ctx = canvas.getContext('2d')!

    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H)

    // Background pill
    const pad = 8, r = 10
    ctx.fillStyle = this.bgColor
    ctx.beginPath()
    ctx.moveTo(pad + r, 4)
    ctx.arcTo(CANVAS_W - pad, 4, CANVAS_W - pad, CANVAS_H - 4, r)
    ctx.arcTo(CANVAS_W - pad, CANVAS_H - 4, pad, CANVAS_H - 4, r)
    ctx.arcTo(pad, CANVAS_H - 4, pad, 4, r)
    ctx.arcTo(pad, 4, CANVAS_W - pad, 4, r)
    ctx.closePath()
    ctx.fill()

    // Skill name (top line, bold)
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 24px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(name, CANVAS_W / 2, CANVAS_H * 0.33, CANVAS_W - pad * 4)

    // Action text (bottom line, lighter)
    ctx.fillStyle = 'rgba(200, 220, 255, 0.9)'
    ctx.font = '18px sans-serif'
    ctx.fillText(action, CANVAS_W / 2, CANVAS_H * 0.7, CANVAS_W - pad * 4)

    return canvas
  }
}
