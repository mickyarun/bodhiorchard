// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * SpaceshipTransport — flies in from the sky, hovers, drops robot, flies away.
 *
 * No beam effect — just the spaceship model flying along a smooth curved path.
 * Uses lerp + easeInOutCubic for natural acceleration/deceleration.
 * Slight banking during turns for realism.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import { AGENT_SPACESHIP } from '../assets/AssetManifest'

const SHIP_SCALE = 0.15
const HOVER_Y = 5             // height above ground when hovering
const SKY_Y = 25              // height at sky edge
const SKY_OFFSET = 35         // horizontal distance from target at sky edge
const FLY_IN_SECS = 2.5
const HOVER_SECS = 0.8        // brief pause before dropping robot
const FLY_OUT_SECS = 2.0
const BANK_ANGLE = 20         // degrees tilt during turns

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}

type FlightPhase = 'idle' | 'fly_in' | 'hovering' | 'fly_out' | 'done'

export class SpaceshipTransport {
  private entity: pc.Entity | null = null
  private phase: FlightPhase = 'idle'
  private timer = 0

  private startPos = new pc.Vec3()
  private hoverPos = new pc.Vec3()
  private exitPos = new pc.Vec3()
  private readonly _scratch = new pc.Vec3()

  private onHoverCb: (() => void) | null = null
  private onGoneCb: (() => void) | null = null
  private _holdHover = false

  async init(parent: pc.Entity, loader: AssetLoader): Promise<void> {
    const asset = await loader.load(AGENT_SPACESHIP)
    const container = asset.resource as { instantiateRenderEntity(): pc.Entity }

    this.entity = new pc.Entity('Spaceship')
    const render = container.instantiateRenderEntity()
    render.setLocalScale(SHIP_SCALE, SHIP_SCALE, SHIP_SCALE)
    this.entity.addChild(render)

    this.entity.enabled = false
    parent.addChild(this.entity)
  }

  /** Fly in from random sky direction to hover above target.
   *  When holdHover is true, ship stays hovering after callback until flyOut() is called. */
  flyIn(targetX: number, targetZ: number, onHover: () => void, holdHover = false): void {
    if (!this.entity) return
    this.onHoverCb = onHover
    this._holdHover = holdHover

    const angle = Math.random() * Math.PI * 2
    const dx = Math.cos(angle) * SKY_OFFSET
    const dz = Math.sin(angle) * SKY_OFFSET

    this.startPos.set(targetX + dx, SKY_Y, targetZ + dz)
    this.hoverPos.set(targetX, HOVER_Y, targetZ)
    this.exitPos.set(targetX - dx * 0.7, SKY_Y, targetZ - dz * 0.7)

    this.entity.setPosition(this.startPos.x, this.startPos.y, this.startPos.z)
    this.entity.enabled = true
    this.phase = 'fly_in'
    this.timer = 0
  }

  /** Fly out from hover position. */
  flyOut(onGone: () => void): void {
    if (!this.entity) return
    this.onGoneCb = onGone
    this.phase = 'fly_out'
    this.timer = 0
  }

  get isActive(): boolean { return this.phase !== 'idle' && this.phase !== 'done' }

  update(dt: number): void {
    if (!this.entity || this.phase === 'idle' || this.phase === 'done') return
    this.timer += dt

    switch (this.phase) {
      case 'fly_in': {
        const t = easeInOutCubic(Math.min(this.timer / FLY_IN_SECS, 1))
        this._scratch.lerp(this.startPos, this.hoverPos, t)
        this.entity.setPosition(this._scratch.x, this._scratch.y, this._scratch.z)
        this.bankToward(this.startPos, this.hoverPos, t)
        if (this.timer >= FLY_IN_SECS) {
          this.phase = 'hovering'
          this.timer = 0
          this.entity.setEulerAngles(0, 0, 0)
        }
        break
      }
      case 'hovering':
        if (this.timer >= HOVER_SECS && this.onHoverCb) {
          this.onHoverCb()
          this.onHoverCb = null
          if (!this._holdHover) {
            this.phase = 'fly_out'
            this.timer = 0
          }
        }
        break
      case 'fly_out': {
        const t = easeInOutCubic(Math.min(this.timer / FLY_OUT_SECS, 1))
        this._scratch.lerp(this.hoverPos, this.exitPos, t)
        this.entity.setPosition(this._scratch.x, this._scratch.y, this._scratch.z)
        this.bankToward(this.hoverPos, this.exitPos, t)
        if (this.timer >= FLY_OUT_SECS) {
          this.entity.enabled = false
          this.phase = 'done'
          this.onGoneCb?.()
          this.onGoneCb = null
        }
        break
      }
    }
  }

  destroy(): void {
    this.entity?.destroy()
    this.entity = null
    this.onHoverCb = null
    this.onGoneCb = null
  }

  reset(): void {
    this.phase = 'idle'
    this.timer = 0
    if (this.entity) this.entity.enabled = false
  }

  private bankToward(from: pc.Vec3, to: pc.Vec3, t: number): void {
    if (!this.entity) return
    const dx = to.x - from.x
    const dz = to.z - from.z
    const yaw = Math.atan2(dx, dz) * pc.math.RAD_TO_DEG
    const bankT = t < 0.5 ? t * 2 : (1 - t) * 2
    this.entity.setEulerAngles(0, yaw, bankT * BANK_ANGLE)
  }
}
