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

/**
 * Physical arc length of the circuit loop, in metres. The loop is drawn
 * ONCE at this size regardless of how many laps a race runs — so a 1-lap
 * and a 2-lap race share an identically-sized course, the difference being
 * how many times racers go around it.
 *
 * The race *distance* (the finish line fed to physics as `trackLengthM`,
 * and the wire value `distanceM`) is `lapCount * LOOP_LENGTH_M`. At
 * LOOP_LENGTH_M = 100 the two allowed distances {100, 200} map cleanly to
 * {1, 2} laps, so all the existing 100/200 distance validation stays valid
 * while the geometry is built from this single fixed length.
 */
export const LOOP_LENGTH_M = 100

/**
 * Lap counts the host may choose. Pairs with ALLOWED_DISTANCES_M through
 * LOOP_LENGTH_M: lap k ⇄ distance k·LOOP_LENGTH_M. The setup dialog shows
 * these as "1 lap" / "2 laps" but still sends `distanceM` on the wire, so
 * the server/backend distance validators need no changes.
 */
export const ALLOWED_LAP_COUNTS = [1, 2] as const
export type AllowedLapCount = typeof ALLOWED_LAP_COUNTS[number]

/** Race distance (finish line) for a given lap count over the fixed loop. */
export function lapCountToDistanceM(lapCount: number): number {
  return lapCount * LOOP_LENGTH_M
}

/** Lap count implied by a race distance over the fixed loop. */
export function distanceMToLapCount(distanceM: number): number {
  return distanceM / LOOP_LENGTH_M
}

/**
 * Track shapes the host may choose when creating a race. Shared between
 * the frontend setup dialog and the multiplayer server validators for the
 * same lock-step reason as ALLOWED_DISTANCES_M. On `circuit` the chosen
 * distance becomes the lap circumference; physics is shape-agnostic.
 */
export const ALLOWED_TRACK_SHAPES = ['straight', 'circuit'] as const

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

// ─── Stamina tuning ─────────────────────────────
//
// Layered on top of the tap-cadence sprint to convert "tap forever" into
// "burst at the right moments." Each tick:
//   * sprinting       → drains stamina at SPRINT_DRAIN_PER_S
//   * walking (move)  → regens at WALK_REGEN_PER_S
//   * idle (no move)  → regens at IDLE_REGEN_PER_S (faster — small
//                       catch-up incentive for trailing racers)
//   * stamina = 0     → sprint window force-clamps to now; further taps
//                       have no effect until stamina recovers
//
// Race-time targets at the 100m distance:
//   Pure sprint (today, stamina cap removed):  ~14s   — no decisions
//   Pure walk:                                 ~33s
//   Optimal pacing (2-3 well-timed bursts):    ~18-22s  — the new sweet spot

/** Stamina is normalized in [0, 1]; the bar UI maps to this directly. */
export const STAMINA_MAX = 1.0

/** Initial stamina at race start. Full so the opening burst is always available. */
export const STAMINA_INITIAL = 1.0

/** Drain per second of active sprint. 0.4 means 2.5s of unbroken sprint
 *  exhausts a full bar — long enough to feel committed, short enough that
 *  pacing matters even on a 100m race. */
export const SPRINT_DRAIN_PER_S = 0.4

/** Regen per second while the move key is held (walking). 0.15 means a
 *  full bar refills in ~6.7s of walking. Pacing-focused: walking can
 *  recover stamina but doesn't out-pace a held sprint over the long run. */
export const WALK_REGEN_PER_S = 0.15

/** Regen per second while idle (no move key). Faster than walk regen so
 *  trailing players have a cheap recovery option, but standing still is
 *  still net-negative on a clock with finite race length. */
export const IDLE_REGEN_PER_S = 0.3

// ─── Boost pads ─────────────────────────────
//
// Glowing strips painted across the track at fixed fractions of the
// PHYSICAL loop. Crossing one grants a free speed burst — faster than a
// sprint and with zero stamina drain. The skill expression is *not*
// sprinting right before a pad: a tap-banked sprint window overlaps the
// boost and wastes both stamina and the differential. On a multi-lap race
// each pad is a single physical strip seen — and fired — once per lap.

/**
 * Pad centres as fractions of the loop length (LOOP_LENGTH_M). Fractions
 * (not metres) so the one fixed loop derives its pad positions from a
 * single definition, and each pad fires once on every lap it's crossed.
 */
export const BOOST_PAD_FRACTIONS = [0.25, 0.5, 0.75] as const

/** Speed target while boosted. Above RUN_TARGET_MPS, below V_MAX_MPS. */
export const BOOST_TARGET_MPS = 9

/** How long one pad's boost lasts from the moment it's crossed. */
export const BOOST_DURATION_MS = 800

// ─── Hurdles ────────────────────────────────
//
// Crossbars at fixed fractions of the PHYSICAL loop. Tapping the jump key
// opens a short airborne window; crossing a hurdle inside the window is
// free, crossing outside it knocks the racer down: velocity drops to
// zero, they spend HURDLE_KNOCKDOWN_MS on the ground (no sprinting or
// jumping while down), lose any banked sprint or boost, and then have to
// accelerate back up from rest. A cooldown between jumps stops "hold
// Space" from trivially clearing everything — timing the jump is the
// mechanic.

/** Hurdle centres as fractions of the loop length (LOOP_LENGTH_M). A bar
 *  is one physical obstacle crossed — and so jumped/clipped — once per lap. */
export const HURDLE_FRACTIONS = [0.35, 0.65] as const

/** Airborne window opened by one jump tap. */
export const HURDLE_JUMP_WINDOW_MS = 400

/**
 * Minimum gap between jump *starts*. With a 400ms window this caps the
 * airborne duty cycle at 40%, so spamming jump clears well under half of
 * the hurdles by luck while a timed jump always clears.
 */
export const HURDLE_JUMP_COOLDOWN_MS = 1000

/**
 * Time spent on the ground after hitting a hurdle — covers the fall and
 * the get-up before the racer can accelerate again from rest. Sized so a
 * missed hurdle costs ~2s versus a clean crossing at sprint speed: a
 * mistake that visibly reorders the field but never feels race-ending
 * with two hurdles per race.
 */
export const HURDLE_KNOCKDOWN_MS = 1500

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

/**
 * Max lifetime of a race in the `lobby` phase with no connected clients.
 *
 * The host may invite a teammate who isn't currently online; the
 * teammate's notification points at a `roomId` that has to still exist
 * by the time they click it. So the RaceRoom disables Colyseus's default
 * `autoDispose` while in lobby and instead falls back to this hard cap.
 * 10 min is the rough timescale of "I sent the invite, switched tabs,
 * and my colleague should have noticed and joined by now."
 *
 * Once the race transitions to `countdown` (i.e. someone hit Start),
 * autoDispose is restored — the room cleans up normally a few seconds
 * after the finish card is dismissed.
 */
export const LOBBY_MAX_MS = 10 * 60 * 1000

/**
 * Grace period between broadcasting `race_cancelled` and disconnecting
 * every client when the host cancels a lobby.
 *
 * Colyseus flushes `broadcast` frames on the next patch tick, but
 * `room.disconnect()` closes sockets synchronously — calling them back to
 * back tears the connection down before the cancel frame is delivered, so
 * the host (and invitees) never receive the message that drives their
 * "back to the garden" navigation. One tick (TICK_MS) plus headroom
 * guarantees the patch goes out first; imperceptible next to the client's
 * own 1.2s toast-then-navigate delay.
 */
export const CANCEL_FLUSH_GRACE_MS = 250
