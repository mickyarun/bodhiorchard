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
 * Lake Fishing — pure game logic for the timing-bar fishing game.
 *
 * Framework-free and shared. The key property that makes this server-ownable:
 * the bobber's position is a DETERMINISTIC function of how long the current
 * cast has been running, so the server can recompute where the bobber really
 * was when a hook arrived and score it itself — the client never reports a
 * score. The server owns the strike-zone position (server-seeded RNG) and the
 * cast clock; the client only renders and sends hook timing.
 */

/** Number of casts in one game. */
export const CASTS = 5
/** Strike-zone width as a fraction of the water (0..1). */
export const ZONE_WIDTH = 0.16

/** Sweep speed jitter band: the per-cast base is scaled by 0.85×..1.35×. */
const SWEEP_JITTER_MIN = 0.85
const SWEEP_JITTER_SPAN = 0.5

/**
 * Base bobber sweep speed (Hz-ish) for a given cast. Speeds up slightly each
 * cast so later casts are harder. `cast` is 0-indexed (0 is the first cast).
 * The live rate is this jittered per cast (see `randomSweepRate`).
 */
export function sweepRateForCast(cast: number): number {
  return 0.9 + cast * 0.18
}

/**
 * A cast's actual sweep speed: the per-cast base, jittered, so the bobber moves
 * at a different speed every play — not just the strike-zone moving. The server
 * picks it (server-seeded) and sends it so the client renders the same curve.
 */
export function randomSweepRate(cast: number, rng: () => number = Math.random): number {
  return sweepRateForCast(cast) * (SWEEP_JITTER_MIN + rng() * SWEEP_JITTER_SPAN)
}

/**
 * A cast's starting phase (0..2 — one full sine period in `t`). With it the
 * bobber no longer always opens dead-centre rising: each cast starts at a
 * different point and direction, so the timing can't be memorised play-to-play.
 */
export function randomPhase(rng: () => number = Math.random): number {
  return rng() * 2
}

/**
 * Bobber position (0..1) `elapsedMs` into a cast with sweep speed `sweepRate`
 * and starting `phase`. A sine sweep: `(sin((t + phase)·π) + 1) / 2`, where `t`
 * advances at `sweepRate` per second. Deterministic in its arguments — the same
 * (elapsed, rate, phase) always yields the same position, which is what lets the
 * server validate a hook authoritatively from the params it chose and sent.
 */
export function bobberPositionAt(elapsedMs: number, sweepRate: number, phase: number): number {
  const t = (elapsedMs / 1000) * sweepRate + phase
  return (Math.sin(t * Math.PI) + 1) / 2
}

/**
 * A fresh strike-zone start position (left edge, 0..1) for the next cast.
 * `rng` is injectable so the server (server-seeded) and tests stay deterministic.
 */
export function randomZoneStart(rng: () => number = Math.random): number {
  return 0.08 + rng() * (0.84 - ZONE_WIDTH)
}

/**
 * Points for a hook: how close the bobber (`marker`) was to the zone centre.
 * 10 (bullseye) / 7 / 4 inside the zone, 0 for a miss. Pure — the server calls
 * this with its own recomputed `marker` and its own `zoneStart`.
 */
export function scoreForHook(marker: number, zoneStart: number): number {
  const center = zoneStart + ZONE_WIDTH / 2
  const offset = Math.abs(marker - center) / (ZONE_WIDTH / 2)
  if (offset > 1) return 0
  if (offset < 0.35) return 10
  if (offset < 0.7) return 7
  return 4
}

/** The maximum achievable score: every cast a bullseye. */
export const FISHING_MAX_SCORE = CASTS * 10
