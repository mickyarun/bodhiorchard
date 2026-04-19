// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * ProximitySystem — detects nearby member characters during takeover mode.
 *
 * Each frame, iterates all characters and finds the closest one within
 * the proximity threshold. Shows their name/presence via TakeoverUI.
 */
import * as pc from 'playcanvas'
import type { CharacterEntity } from '../characters/CharacterFactory'
import type { TakeoverUI } from './TakeoverUI'

const PROXIMITY_THRESHOLD_SQ = 3.0 * 3.0  // 3 world units, squared

export class ProximitySystem {
  private lastShownId: string | null = null

  /**
   * Check proximity to all characters and show/hide member info.
   * @param playerPos - Current player position
   * @param playerId - Player's own member ID (skip self)
   * @param characters - All character entities in the scene
   * @param ui - TakeoverUI for showing/hiding member info
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
      ui.showMemberInfo(closestName, 'Nearby')
      this.lastShownId = closestId
    } else if (!closestId && this.lastShownId) {
      ui.hideMemberInfo()
      this.lastShownId = null
    }
  }

  /** Whether a non-self character is currently within proximity range. */
  get hasNearbyMember(): boolean { return this.lastShownId !== null }

  /** The memberId of the nearest character, or null if none nearby. */
  get nearbyMemberId(): string | null { return this.lastShownId }

  reset(): void {
    this.lastShownId = null
  }
}
