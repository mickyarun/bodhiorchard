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
 * Public types for the race module.
 *
 * Kept separate from index.ts so backend/multiplayer packages can import
 * these type definitions without pulling in any PlayCanvas dependencies.
 */

export type RaceMode = 'solo' | 'live'

export interface RaceInitOptions {
  mode: RaceMode
  /** Required when mode === 'live'. Ignored in solo mode. */
  roundId?: string
  width: number
  height: number
}

// Pure types that both the frontend and the Colyseus server need live in
// `/shared/race/types.ts`. Re-exporting (import-then-re-export) so existing
// `@/engine/race` consumers keep their imports AND the types are usable
// in the field declarations below.
import type { RacePhase, Placing } from '@shared/race/types'
export type { RacePhase, Placing }

/** Per-racer HUD-facing snapshot. Read by Vue components each frame. */
export interface RaceHudSlot {
  /** Display name sourced from the racer's preset (e.g. 'Blaze'). */
  name: string
  /** Human-readable move-key label (e.g. 'W', '↑'). */
  moveLabel: string
  /** Human-readable sprint-modifier label (e.g. 'L-Shift'). */
  sprintLabel: string
  /** True once the player has pressed their move key to join this round. */
  joined: boolean
  /** Live distance travelled in metres (0 until running). */
  positionM: number
  /** Live velocity in m/s. */
  velocityMps: number
  /** True while the move key is held (only meaningful in running phase). */
  isMoving: boolean
  /** True while the sprint modifier is held. */
  isSprinting: boolean
  /** True once this racer has crossed the finish line. */
  finished: boolean
  /** 1-based place after the race ends; null before `finished` phase. */
  place: number | null
}

/**
 * Snapshot of everything the HUD needs to render one frame.
 *
 * The controller exposes this via a synchronous getter; Vue components
 * poll it inside a requestAnimationFrame loop. Fields are all primitives
 * or frozen arrays so reads are allocation-free at steady state.
 */
export interface RaceHudState {
  phase: RacePhase
  /** Ms since the current phase began. Useful for countdown / timer display. */
  phaseElapsedMs: number
  /** Ms remaining on the countdown (0 outside countdown phase). */
  countdownRemainingMs: number
  /** Ms since the running phase began (0 outside running + finished). */
  runningElapsedMs: number
  /** Number of slots currently joined — drives the lobby UI. */
  joinedCount: number
  /** Per-racer state. */
  slots: readonly RaceHudSlot[]
  /** Length of the race in metres — used for normalising progress bars. */
  trackLengthM: number
  /** Finalised placings after the `finished` phase begins. null otherwise. */
  placings: readonly Placing[] | null
}
