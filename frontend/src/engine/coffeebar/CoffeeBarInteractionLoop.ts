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
 * CoffeeBarInteractionLoop — per-frame proximity + E-key logic for the
 * coffee machine.
 *
 * Drives the proximity prompt and the three E-key actions:
 *   1. "[E] Order a drink"   → open the drink menu
 *   2. "[E] Take your drink" → send coffee_ack_dispense (phase=dispensed && mine)
 *   3. "Queue position: N"   → info-only (no E action while queued)
 *
 * Mirrors the shape of interior/InteractionLoop.ts (pure logic, no entity
 * creation). The scene/state read lives here; the UI and room client are
 * passed in so this class stays framework-agnostic.
 */
import * as pc from 'playcanvas'
import type { PlayerController } from '../housetest/PlayerController'
import type { InputManager } from '../input/InputManager'
import type { CoffeeBarUI } from './CoffeeBarUI'
import type { CoffeeBarRoomClient, CoffeeBarSnapshot } from './CoffeeBarRoomClient'
import { COFFEE_MACHINE_POS } from './SceneConfig'

/** Proximity radius around the machine that triggers the prompt. */
const MACHINE_RADIUS_SQ = 1.3 * 1.3

export class CoffeeBarInteractionLoop {
  private ePrev = false
  private menuOpen = false

  /** Fires once when the local player presses E during the 'take' action.
   *  Manager hooks this to play the drink animation + speech bubble. */
  onDrinkTaken: (() => void) | null = null

  /** Read by CoffeeBarUI to know whether to render the menu. */
  get isMenuOpen(): boolean { return this.menuOpen }

  openMenu(): void { this.menuOpen = true }
  closeMenu(): void { this.menuOpen = false }

  reset(): void {
    this.ePrev = false
    this.menuOpen = false
  }

  /**
   * Run one frame. Returns true if the menu should be shown (consumed by
   * CoffeeBarManager so it can pass the correct drink list to the UI).
   */
  update(
    player: PlayerController,
    input: InputManager,
    ui: CoffeeBarUI,
    roomClient: CoffeeBarRoomClient,
    localUserId: string,
  ): void {
    const snapshot = roomClient.snapshot
    const near = this.isNearMachine(player)
    const eDown = input.isPressed(pc.KEY_E)
    const eJust = eDown && !this.ePrev
    this.ePrev = eDown

    // Menu open takes precedence — UI handles its own button clicks, but the
    // prompt should stay hidden while picking a drink.
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
        ui.showPrompt('[E] Order a drink')
        if (eJust) this.menuOpen = true
        break
      case 'take':
        ui.showPrompt('[E] Take your drink')
        if (eJust) {
          roomClient.ackDispense()
          this.onDrinkTaken?.()
        }
        break
      case 'queued':
        ui.showPrompt(`Queue position: ${action.position}`)
        break
      case 'busy':
        ui.showPrompt(`Serving: ${action.drink}`)
        break
    }
  }

  private isNearMachine(player: PlayerController): boolean {
    const pos = player.getPosition()
    const dx = pos.x - COFFEE_MACHINE_POS.x
    const dz = pos.z - COFFEE_MACHINE_POS.z
    return dx * dx + dz * dz < MACHINE_RADIUS_SQ
  }

  private resolveAction(
    snapshot: CoffeeBarSnapshot,
    localUserId: string,
  ):
    | { kind: 'order' }
    | { kind: 'take' }
    | { kind: 'queued'; position: number }
    | { kind: 'busy'; drink: string } {
    const active = snapshot.active

    // My drink is dispensed — I can take it.
    if (active.phase === 'dispensed' && active.userId === localUserId) {
      return { kind: 'take' }
    }

    // I'm being served (approaching / brewing) — stand and wait.
    if (active.userId === localUserId && active.phase !== 'idle') {
      return { kind: 'busy', drink: active.drink || 'your drink' }
    }

    // I'm in the queue — show position (1-indexed).
    const idx = snapshot.queue.indexOf(localUserId)
    if (idx >= 0) return { kind: 'queued', position: idx + 1 }

    // Default: offer to order.
    return { kind: 'order' }
  }
}
