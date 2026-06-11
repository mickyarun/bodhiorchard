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
 * LoopPath — arc-length → world-pose mapping for the organic circuit loop.
 *
 * Pure math, framework-free, like the rest of shared/race. Replaces the
 * perfect circle of CircuitGeometry as the rendered circuit shape: the
 * loop's radius is modulated by FIXED low-order harmonics so the track
 * reads as a hand-drawn closed course instead of a geometric ring. No
 * randomness anywhere — every client (and any future server consumer)
 * derives the identical shape from the circumference alone.
 *
 * Construction (cached per circumference):
 *   1. Sample r(φ) = 1 + A2·sin(2φ+P2) + A3·sin(3φ+P3) at SAMPLE_COUNT
 *      points and accumulate a chord-length table.
 *   2. Scale every point by circumferenceM / sampledLength. Scaling is a
 *      pure radial homothety, so arc length scales linearly and the
 *      table's total equals circumferenceM exactly.
 *   3. Anchor: rotate + translate the samples once so the φ=0 sample is
 *      the world origin with heading 0 (+X) — the same start-line frame
 *      the straight track and CircuitGeometry use.
 *
 * Conventions (parity with circuitPose, asserted in LoopPath.test.ts):
 *   - pose(0, C, lateral) = (0, lateral), heading 0 — positive lateral
 *     offsets point along the inward normal, which at arc 0 is +Z,
 *     matching the straight track's lane direction.
 *   - headingRad grows monotonically from 0 to 2π over one lap (the loop
 *     is convex by construction — see the curvature-radius test), so
 *     consumers can lerp it without unwrapping.
 */

/**
 * Radial harmonic amplitudes/phases (fractions of the base radius,
 * radians). Chosen so the loop is clearly non-circular (~24% peak-to-peak
 * radial variation about the centroid) while the numerically-measured
 * minimum curvature radius at the 100 m circumference stays ≈10.7 m —
 * comfortably above the (MAX_RACERS·LANE_WIDTH_M)/2 + 1 m = 8.5 m bound
 * below which the widest track's inner lane edge would self-intersect.
 * Locked by the curvature test in LoopPath.test.ts; retune all four
 * together if the shape ever changes.
 */
const HARMONIC_2_AMPLITUDE = 0.08
const HARMONIC_2_PHASE_RAD = 0.7
const HARMONIC_3_AMPLITUDE = 0.05
const HARMONIC_3_PHASE_RAD = 2.3

/**
 * Polar samples taken around the loop. 2048 keeps the worst-case chord
 * error far below visual scale (sub-mm at 200 m) and the per-circumference
 * table build under a millisecond; lookups are O(log n) binary searches.
 */
const SAMPLE_COUNT = 2048

/** World-space pose for an avatar / prop on the loop. */
export interface LoopPose {
  x: number
  z: number
  /**
   * Direction of travel about +Y in radians, measured from +X toward +Z.
   * 0 at the start line, 2π after one lap, monotonic in between.
   */
  headingRad: number
}

/** Axis-aligned bounds of the loop's centreline path. */
export interface LoopBounds {
  minX: number
  maxX: number
  minZ: number
  maxZ: number
}

interface LoopTable {
  /** Cumulative arc length per sample; arcs[SAMPLE_COUNT] === circumferenceM. */
  arcs: Float64Array
  xs: Float64Array
  zs: Float64Array
  /** Unwrapped tangent angle per sample — 0 at index 0, 2π at the end. */
  headings: Float64Array
  bounds: LoopBounds
}

/** One table per circumference — the race only ever uses two (100, 200). */
const tableCache = new Map<number, LoopTable>()

/** Radius modulation at polar angle φ (about a unit base radius). */
function radiusAt(phi: number): number {
  return (
    1 +
    HARMONIC_2_AMPLITUDE * Math.sin(2 * phi + HARMONIC_2_PHASE_RAD) +
    HARMONIC_3_AMPLITUDE * Math.sin(3 * phi + HARMONIC_3_PHASE_RAD)
  )
}

function buildTable(circumferenceM: number): LoopTable {
  const n = SAMPLE_COUNT
  const us = new Float64Array(n + 1)
  const vs = new Float64Array(n + 1)
  const arcs = new Float64Array(n + 1)
  for (let i = 0; i <= n; i++) {
    const phi = (i / n) * 2 * Math.PI
    const r = radiusAt(phi)
    us[i] = r * Math.cos(phi)
    vs[i] = r * Math.sin(phi)
    if (i > 0) arcs[i] = arcs[i - 1] + Math.hypot(us[i] - us[i - 1], vs[i] - vs[i - 1])
  }

  // Radial scaling scales chord (and therefore arc) length linearly, so
  // after this the cumulative table totals circumferenceM exactly.
  const scale = circumferenceM / arcs[n]
  for (let i = 0; i <= n; i++) {
    us[i] *= scale
    vs[i] *= scale
    arcs[i] *= scale
  }

  // Tangent angles, unwrapped to be monotonic. The seam sample (i === n)
  // shares the start tangent plus one full turn. Forward differences with
  // the periodic neighbour keep the heading consistent at the wrap.
  const headings = new Float64Array(n + 1)
  let prev = Math.atan2(vs[1] - vs[0], us[1] - us[0])
  headings[0] = prev
  for (let i = 1; i < n; i++) {
    let h = Math.atan2(vs[i + 1] - vs[i], us[i + 1] - us[i])
    while (h < prev - Math.PI) h += 2 * Math.PI
    while (h > prev + Math.PI) h -= 2 * Math.PI
    headings[i] = h
    prev = h
  }
  headings[n] = headings[0] + 2 * Math.PI

  // Anchor: rotate by −headings[0] so the start tangent is +X, then
  // translate the start sample to the origin. The natural frame's CCW
  // turn maps onto "heading grows from +X toward +Z" without reflection,
  // so positive lateral (inward normal) lands on +Z at arc 0 — the same
  // sign convention as circuitPose and the straight track.
  const startHeading = headings[0]
  const cosA = Math.cos(-startHeading)
  const sinA = Math.sin(-startHeading)
  const xs = new Float64Array(n + 1)
  const zs = new Float64Array(n + 1)
  const bounds: LoopBounds = { minX: Infinity, maxX: -Infinity, minZ: Infinity, maxZ: -Infinity }
  for (let i = 0; i <= n; i++) {
    const du = us[i] - us[0]
    const dv = vs[i] - vs[0]
    xs[i] = du * cosA - dv * sinA
    zs[i] = du * sinA + dv * cosA
    headings[i] -= startHeading
    if (xs[i] < bounds.minX) bounds.minX = xs[i]
    if (xs[i] > bounds.maxX) bounds.maxX = xs[i]
    if (zs[i] < bounds.minZ) bounds.minZ = zs[i]
    if (zs[i] > bounds.maxZ) bounds.maxZ = zs[i]
  }

  return { arcs, xs, zs, headings, bounds }
}

function getTable(circumferenceM: number): LoopTable {
  let table = tableCache.get(circumferenceM)
  if (!table) {
    table = buildTable(circumferenceM)
    tableCache.set(circumferenceM, table)
  }
  return table
}

/** Largest index i with arcs[i] <= arc (binary search over the table). */
function lowerIndex(arcs: Float64Array, arc: number): number {
  let lo = 0
  let hi = arcs.length - 1
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1
    if (arcs[mid] <= arc) lo = mid
    else hi = mid
  }
  return lo
}

/**
 * Map a centreline arc length to the world pose for a point offset
 * `lateralOffsetM` from the centreline. Positive offsets sit toward the
 * inside of the loop (the inward normal), mirroring circuitPose — at the
 * start line that normal is +Z, the straight track's lane direction.
 * Arc lengths beyond one lap extend heading past 2π (no wrap), exactly
 * like circuitPose, so finish-band consumers keep working.
 */
export function loopPose(
  arcLengthM: number,
  circumferenceM: number,
  lateralOffsetM = 0,
): LoopPose {
  const table = getTable(circumferenceM)
  const laps = Math.floor(arcLengthM / circumferenceM)
  const arc = arcLengthM - laps * circumferenceM
  const i = lowerIndex(table.arcs, arc)
  const span = table.arcs[i + 1] - table.arcs[i]
  const t = span > 0 ? (arc - table.arcs[i]) / span : 0

  const x = table.xs[i] + (table.xs[i + 1] - table.xs[i]) * t
  const z = table.zs[i] + (table.zs[i + 1] - table.zs[i]) * t
  const heading = table.headings[i] + (table.headings[i + 1] - table.headings[i]) * t

  // Inward normal = heading rotated a quarter turn toward +Z (verified
  // against the circle: at heading θ it equals (−sin θ, cos θ)).
  return {
    x: x - lateralOffsetM * Math.sin(heading),
    z: z + lateralOffsetM * Math.cos(heading),
    headingRad: heading + laps * 2 * Math.PI,
  }
}

/**
 * Axis-aligned bounding box of the loop's centreline. Consumers framing
 * the whole course (overhead camera, ground plane) expand this by the
 * half track width plus their own margin.
 */
export function loopBounds(circumferenceM: number): LoopBounds {
  return { ...getTable(circumferenceM).bounds }
}
