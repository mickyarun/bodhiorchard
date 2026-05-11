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
 * Race tuning constants — pure values, no runtime dependencies.
 *
 * This file (and RacePhysics.ts) are explicitly free of PlayCanvas
 * and framework imports so they can be hoisted into a shared package
 * in Phase 2 without rework. Don't add non-pure imports here.
 */

/**
 * Default race distance — used by `RacePhysics.tick` only when a caller
 * doesn't supply a per-room `trackLengthM`. The production race-v2 path
 * (RaceRoom + RaceScene) always passes the room's chosen distance; this
 * default exists solely to keep the physics unit tests terse.
 */
export const TRACK_LENGTH_M = 60

/**
 * Distances the host may choose when creating a race. Shared between the
 * frontend setup dialog, the multiplayer server validator, and the backend
 * write-path validator so the three stay in lock-step.
 */
export const ALLOWED_DISTANCES_M = [100, 200] as const
export type AllowedDistanceM = typeof ALLOWED_DISTANCES_M[number]

/** Inclusive bounds on participant count per race-v2 room. */
export const MIN_RACERS = 2
export const MAX_RACERS = 10

/**
 * Width of a single running lane in metres. Track width is computed as
 * `laneCount * LANE_WIDTH_M` — scales from a 2-lane 3m-wide road up to a
 * 10-lane 15m-wide road without any magic-number changes elsewhere.
 */
export const LANE_WIDTH_M = 1.5

// ─── Physics tuning ─────────────────────────────
//
// Mechanic (2026-04-19 redesign v3):
//   - HOLD the "move" key (W or ↑) → character walks forward.
//   - TAP the sprint key (Shift) → adds a short sprint burst. Rapid
//     tapping keeps the sprint active; skipping taps drops back to walk.
//   - Release the move key → decelerates to rest.
//
// Holding shift would race toward a deterministic steady state (both
// players hit RUN_TARGET_MPS and cross simultaneously — exactly what
// happened in the first playtest). The tap mechanic restores player
// skill: tap cadence directly controls average speed.
//
// Race-time ballpark at the 60m track:
//   Walk only:            60 / 3    = 20.0s
//   Sustained tap (≥4/s): 60 / 7    = ~8.6s
//   Mid-cadence (~2/s):   60 / 5    = ~12s (half walk / half sprint)

/** Steady-state speed while move key held without sprint (walk). */
export const WALK_TARGET_MPS = 3

/** Peak speed reached during an active sprint burst. */
export const RUN_TARGET_MPS = 7

/** Acceleration toward the current target while the move key is held (m/s²). */
export const MOVE_ACCEL_MPSS = 12

/** Deceleration when the move key is released (m/s²). */
export const MOVE_DECEL_MPSS = 10

/**
 * Each sprint-key tap extends the sprint window by this many ms.
 * At 250ms per tap, a player needs ≥ 4 taps/sec to sustain full sprint —
 * achievable but meaningfully skill-dependent.
 */
export const SPRINT_TAP_DURATION_MS = 250

/**
 * Maximum sprint window that can be banked from rapid tapping. Prevents
 * a tap-once-and-forget exploit. 600ms = 2.4× one tap's duration.
 */
export const SPRINT_MAX_WINDOW_MS = 600

/** Hard ceiling — safety cap in case of future tuning. */
export const V_MAX_MPS = 12

/**
 * Server / live-mode sim tick period. Matches Colyseus 20Hz.
 *
 * NOTE: in local (Phase 1) mode the physics runs at render rate — whatever
 * `dt` the frame gives us — for smooth visuals. This constant is kept only
 * for the Phase 2 server tick rate and for backwards compatibility with the
 * determinism test suite.
 */
export const TICK_MS = 50

/** Countdown phase duration before running starts. */
export const COUNTDOWN_MS = 3000

/**
 * Hard timeout for the running phase — any racer still mid-track when it
 * fires is recorded as DNF. Sized for the slowest legitimate run: 200 m
 * at steady walk (WALK_TARGET_MPS = 3) takes ~67 s; 120 s gives that
 * roughly a 2× buffer for stragglers, tap-throttled sprints, and lag.
 */
export const RUNNING_TIMEOUT_MS = 120000

/** How long the final placings card is shown before the scene resets. */
export const FINISHED_DISPLAY_MS = 10000
