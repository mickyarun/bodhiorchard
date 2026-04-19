// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * InteractableItem — a named world object the player can interact with.
 *
 * Each frame, HouseTestEngine checks proximity. When the player is within
 * `interactRadius`, the UI shows the prompt. Pressing E fires onUse().
 *
 * Constructed from InteractableDef (SceneConfig.ts) — all data lives there.
 */
import * as pc from 'playcanvas'
import type { ActionType, InteractableId, SeatConfig } from './SceneConfig'

const DEFAULT_RADIUS = 1.3

export class InteractableItem {
  readonly id: InteractableId
  readonly worldPos: pc.Vec3
  readonly promptText: string
  readonly infoText: string
  readonly action: ActionType
  readonly seat: SeatConfig | undefined
  readonly interactRadius: number

  private _onUse: (() => void) | null = null

  constructor(
    id: InteractableId,
    worldPos: pc.Vec3,
    promptText: string,
    infoText: string,
    action: ActionType,
    seat?: SeatConfig,
    radius = DEFAULT_RADIUS,
  ) {
    this.id           = id
    this.worldPos     = worldPos
    this.promptText   = promptText
    this.infoText     = infoText
    this.action       = action
    this.seat         = seat
    this.interactRadius = radius
  }

  isNear(playerPos: pc.Vec3): boolean {
    const dx = playerPos.x - this.worldPos.x
    const dz = playerPos.z - this.worldPos.z
    return Math.sqrt(dx * dx + dz * dz) < this.interactRadius
  }

  onUse(fn: () => void): void { this._onUse = fn }
  use(): void { this._onUse?.() }
}
