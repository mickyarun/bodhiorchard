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
 * CafeteriaInteractionLoop — per-frame proximity + E-key logic for the
 * cafeteria food counter.
 *
 * Mirrors CoffeeBarInteractionLoop with meal-oriented prompts. Three
 * E-key actions when near the counter:
 *   1. "[E] Order food"     → open the food menu
 *   2. "[E] Take your meal" → send cafe_ack_dispense (phase=dispensed && mine)
 *   3. "Queue position: N"  → info-only (no E action while queued)
 */
import * as pc from 'playcanvas'
import type { PlayerController } from '../housetest/PlayerController'
import type { InputManager } from '../input/InputManager'
import type { CafeteriaUI } from './CafeteriaUI'
import type { CafeteriaRoomClient, CafeteriaSnapshot } from './CafeteriaRoomClient'
import { FOOD_COUNTER_POS } from './SceneConfig'

/** Prompt radius around FOOD_COUNTER_POS. Counter is only ~1 m wide, so a
 *  tight 0.9 m radius keeps "[E] Order food" from triggering while the
 *  player is seated at a nearby table. */
const COUNTER_RADIUS_SQ = 0.9 * 0.9

export class CafeteriaInteractionLoop {
  private ePrev = false
  private menuOpen = false

  /** Fires once when the local player presses E during the 'take' action. */
  onMealTaken: (() => void) | null = null

  get isMenuOpen(): boolean { return this.menuOpen }

  openMenu(): void { this.menuOpen = true }
  closeMenu(): void { this.menuOpen = false }

  reset(): void {
    this.ePrev = false
    this.menuOpen = false
  }

  update(
    player: PlayerController,
    input: InputManager,
    ui: CafeteriaUI,
    roomClient: CafeteriaRoomClient,
    localUserId: string,
  ): void {
    const snapshot = roomClient.snapshot
    const near = this.isNearCounter(player)
    const eDown = input.isPressed(pc.KEY_E)
    const eJust = eDown && !this.ePrev
    this.ePrev = eDown

    if (this.menuOpen) {
      ui.hidePrompt()
      return
    }

    if (!near) {
      ui.hidePrompt()
      return
    }

    const action = this.resolveAction(snapshot, localUserId)

    switch (action.kind) {
      case 'order':
        ui.showPrompt('[E] Order food')
        if (eJust) this.menuOpen = true
        break
      case 'take':
        ui.showPrompt('[E] Take your meal')
        if (eJust) {
          roomClient.ackDispense()
          this.onMealTaken?.()
        }
        break
      case 'queued':
        ui.showPrompt(`Queue position: ${action.position}`)
        break
      case 'busy':
        ui.showPrompt(`Serving: ${action.meal}`)
        break
    }
  }

  private isNearCounter(player: PlayerController): boolean {
    const pos = player.getPosition()
    const dx = pos.x - FOOD_COUNTER_POS.x
    const dz = pos.z - FOOD_COUNTER_POS.z
    return dx * dx + dz * dz < COUNTER_RADIUS_SQ
  }

  private resolveAction(
    snapshot: CafeteriaSnapshot,
    localUserId: string,
  ):
    | { kind: 'order' }
    | { kind: 'take' }
    | { kind: 'queued'; position: number }
    | { kind: 'busy'; meal: string } {
    const active = snapshot.active

    if (active.phase === 'dispensed' && active.userId === localUserId) {
      return { kind: 'take' }
    }

    if (active.userId === localUserId && active.phase !== 'idle') {
      return { kind: 'busy', meal: active.meal || 'your meal' }
    }

    const idx = snapshot.queue.indexOf(localUserId)
    if (idx >= 0) return { kind: 'queued', position: idx + 1 }

    return { kind: 'order' }
  }
}
