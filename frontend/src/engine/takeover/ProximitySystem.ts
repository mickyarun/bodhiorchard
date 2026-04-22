// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * ProximitySystem — detects nearby member characters during takeover mode.
 *
 * Each frame, iterates all characters and finds the closest one within
 * the proximity threshold. Shows their name/presence via TakeoverUI.
 */
import * as pc from 'playcanvas'
import type { CharacterEntity } from '../characters/CharacterTypes'
import type { TakeoverUI } from './TakeoverUI'

const PROXIMITY_THRESHOLD_SQ = 3.0 * 3.0  // 3 world units, squared

export class ProximitySystem {
  private lastShownId: string | null = null
  private lastShownName: string = ''

  /**
   * Check proximity to all characters and show/hide the action panel.
   * The panel always carries the targeted member's userId + name so the
   * Greet / Invite-to-race buttons know who they're acting on.
   */
  update(
    playerPos: pc.Vec3,
    playerId: string,
    characters: CharacterEntity[],
    ui: TakeoverUI,
  ): void {
    let closestId: string | null = null
    let closestName = ''
    let closestDistSq = PROXIMITY_THRESHOLD_SQ

    for (const char of characters) {
      if (char.memberId === playerId) continue

      const pos = char.entity.getPosition()
      const dx = pos.x - playerPos.x
      const dz = pos.z - playerPos.z
      const distSq = dx * dx + dz * dz

      if (distSq < closestDistSq) {
        closestDistSq = distSq
        closestId = char.memberId
        closestName = char.memberName
      }
    }

    if (closestId && closestId !== this.lastShownId) {
      ui.showMemberActionPanel(closestId, closestName)
      this.lastShownId = closestId
      this.lastShownName = closestName
    } else if (!closestId && this.lastShownId) {
      ui.hideMemberActionPanel()
      this.lastShownId = null
      this.lastShownName = ''
    }
  }

  /** Whether a non-self character is currently within proximity range. */
  get hasNearbyMember(): boolean { return this.lastShownId !== null }

  /** The memberId of the nearest character, or null if none nearby. */
  get nearbyMemberId(): string | null { return this.lastShownId }

  /** The display name of the nearest character, or an empty string. */
  get nearbyMemberName(): string { return this.lastShownName }

  reset(): void {
    this.lastShownId = null
    this.lastShownName = ''
  }
}
