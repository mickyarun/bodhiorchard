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
 * RaceHudStateBuilder — constructs the RaceHudState snapshot the HUD reads
 * every frame, reusing a pre-allocated slot buffer so steady-state polling
 * is allocation-free.
 */
import type { RacerAvatar } from './RacerAvatar'
import type { Racer } from '@shared/race/RacePhysics'
import type { Placing, RacePhase, RaceHudSlot, RaceHudState } from './types'
import { COUNTDOWN_MS } from '@shared/race/RaceConstants'

/**
 * Key-binding labels per racer — used only by the HUD for rendering.
 * Replaces the deleted `PlayerSlot` type from the previous controller.
 * Step 2 of the race-v2 rebuild will re-home this into a shared types file
 * when the new `RaceRoomClient` lands.
 */
export interface HudKeyLabels {
  moveLabel: string
  sprintLabel: string
}

export interface HudSourceState {
  phase: RacePhase
  phaseStartMs: number
  runningElapsedMs: number
  joined: readonly boolean[]
  racers: readonly Racer[]
  avatars: readonly RacerAvatar[]
  slots: readonly HudKeyLabels[]
  trackLengthM: number
  placings: readonly Placing[] | null
}

export class RaceHudStateBuilder {
  /** Pre-allocated slot buffer — mutated in place on every snapshot read. */
  private readonly hudSlotBuffer: RaceHudSlot[]

  constructor(avatars: readonly RacerAvatar[], slots: readonly HudKeyLabels[]) {
    this.hudSlotBuffer = avatars.map((a, i) => ({
      name: a.displayName,
      moveLabel: slots[i].moveLabel,
      sprintLabel: slots[i].sprintLabel,
      joined: false,
      positionM: 0,
      velocityMps: 0,
      isMoving: false,
      isSprinting: false,
      finished: false,
      place: null,
    }))
  }

  build(src: HudSourceState): RaceHudState {
    const phaseElapsedMs = performance.now() - src.phaseStartMs
    const countdownRemainingMs = src.phase === 'countdown'
      ? Math.max(0, COUNTDOWN_MS - phaseElapsedMs)
      : 0

    const nowMs = src.runningElapsedMs
    for (let i = 0; i < src.racers.length; i++) {
      const r = src.racers[i]
      const slot = this.hudSlotBuffer[i]
      slot.joined = src.joined[i]
      slot.positionM = r.positionM
      slot.velocityMps = r.velocityMps
      slot.isMoving = r.isMoving
      slot.isSprinting = nowMs < r.sprintUntilMs
      slot.finished = r.finished
      slot.place = this.placeForRacer(src.placings, r.id)
    }

    let joinedCount = 0
    for (const j of src.joined) if (j) joinedCount++

    return {
      phase: src.phase,
      phaseElapsedMs,
      countdownRemainingMs,
      runningElapsedMs: src.runningElapsedMs,
      joinedCount,
      slots: this.hudSlotBuffer,
      trackLengthM: src.trackLengthM,
      placings: src.placings,
    }
  }

  private placeForRacer(placings: readonly Placing[] | null, racerId: string): number | null {
    if (!placings) return null
    for (const p of placings) if (p.racerId === racerId) return p.place
    return null
  }
}
