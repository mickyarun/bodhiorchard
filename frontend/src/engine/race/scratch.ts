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
