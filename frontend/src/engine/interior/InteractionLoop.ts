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
 * InteractionLoop — per-frame interactable proximity and E-key logic.
 *
 * Extracted from HouseTestEngine.onUpdate() to keep InteriorManager lean.
 * Pure logic — no entity creation or DOM manipulation.
 */
import * as pc from 'playcanvas'
import type { InteractableItem } from '../housetest/InteractableItem'
import type { InteriorScene } from '../housetest/InteriorScene'
import type { PlayerController } from '../housetest/PlayerController'
import type { InputManager } from '../input/InputManager'
import type { InteriorUI } from './InteriorUI'
import type { InteractableId } from '../housetest/SceneConfig'

export class InteractionLoop {
  private ePrev = false
  private activeSeatId: InteractableId | null = null

  /**
   * Run one frame of interaction checks.
   * Returns true if player state changed (sat down / woke up).
   */
  update(
    player: PlayerController,
    input: InputManager,
    scene: InteriorScene,
    ui: InteriorUI,
  ): void {
    const playerPos = player.getPosition()
    const eDown = input.isPressed(pc.KEY_E)
    const eJust = eDown && !this.ePrev
    this.ePrev = eDown

    if (eJust) {
      if (player.isSitting) { player.standUp() }
      else if (player.isSleeping) { player.wakeUp() }
      else {
        for (const item of scene.items) {
          if (item.isNear(playerPos)) { item.use(); break }
        }
      }
    }

    // Clean up effects when player leaves seated/sleeping state (via WASD)
    if (this.activeSeatId !== null && !player.isSitting && !player.isSleeping) {
      if (this.activeSeatId === 'tv') scene.tvEffect.turnOff()
      this.activeSeatId = null
    }

    // Show/hide proximity prompts
    this.updatePrompts(playerPos, scene.items, ui)
  }

  /** Drive TV flicker with accurate dt from frame loop. */
  updateTV(dt: number, scene: InteriorScene): void {
    scene.tvEffect.update(dt)
  }

  /** Track which seat is active (for effect cleanup). */
  setActiveSeat(id: InteractableId): void {
    this.activeSeatId = id
  }

  reset(): void {
    this.ePrev = false
    this.activeSeatId = null
  }

  private updatePrompts(
    playerPos: pc.Vec3,
    items: readonly InteractableItem[],
    ui: InteriorUI,
  ): void {
    for (const item of items) {
      if (item.isNear(playerPos)) {
        ui.showPrompt(item.promptText)
        return
      }
    }
    ui.hidePrompt()
  }
}
