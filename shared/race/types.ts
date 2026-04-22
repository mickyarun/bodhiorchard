// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
