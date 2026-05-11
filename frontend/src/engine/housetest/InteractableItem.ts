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
