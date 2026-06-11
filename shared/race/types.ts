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
 * Pure race types shared between the frontend client and the Colyseus
 * multiplayer server. Anything client- or render-specific (HUD state,
 * RaceEngine init options, etc.) stays in the frontend's types.ts.
 *
 * Zero runtime imports — this file is pure TypeScript so both build
 * pipelines can consume it without additional plumbing.
 */

/** Race round lifecycle — single source of truth for both client and server. */
export type RacePhase = 'lobby' | 'countdown' | 'running' | 'finished'

/**
 * Track layout chosen by the host at race-create time.
 *
 * Physics treats `positionM` as a 1-D scalar either way: on a straight
 * track it's the world X, on a circuit it's the arc length along the
 * loop centreline. The loop has a fixed length; the race distance is
 * `lapCount × loop length`, so `positionM` climbs past one loop on a
 * multi-lap race. Only renderers map the scalar to world space, via
 * `LoopPath` (the circuit's organic closed loop).
 */
export type TrackShape = 'straight' | 'circuit'

/**
 * Finish ranking entry for a single racer. Produced by
 * RacePhysics.checkFinish on the server; mirrored to clients via the
 * Colyseus schema; consumed by both the client HUD and (later) the
 * backend XP payout.
 */
export interface Placing {
  racerId: string
  /** 1-based finish place. */
  place: number
  /** True if the racer crossed the finish line before the round ended. */
  finished: boolean
  /** Ms since race start at the crossing; 0 for DNFs. */
  finishTimeMs: number
  /** Final x-position along the track (used to rank DNFs). */
  distanceM: number
}
