// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * scratch — pre-allocated PlayCanvas vector/quat instances reused inside
 * hot per-frame paths to avoid GC pauses.
 *
 * Convention: callers MUST use these within a single call site, never hold
 * references across calls or async boundaries. The pool is small on purpose —
 * if a new caller needs a slot that's already borrowed, either (a) use a
 * different scratch, or (b) restructure to avoid concurrent usage.
 *
 * Follows PlayCanvas's official optimization guidance:
 *   https://developer.playcanvas.com/user-manual/optimization/guidelines/
 *   — "Pre-allocate objects in initialization rather than creating them
 *     repeatedly to avoid garbage collection freezes."
 */
import * as pc from 'playcanvas'

/** Scratch Vec3 slots. Name-suffixed A/B/C/D for unambiguous site mapping. */
export const SCRATCH_VEC3_A = new pc.Vec3()
export const SCRATCH_VEC3_B = new pc.Vec3()
export const SCRATCH_VEC3_C = new pc.Vec3()
export const SCRATCH_VEC3_D = new pc.Vec3()
