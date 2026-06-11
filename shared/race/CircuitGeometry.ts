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
 * CircuitGeometry — arc-length → world-pose mapping for the circular track.
 *
 * Pure math, framework-free, like the rest of shared/race. The physics
 * keeps treating `positionM` as a 1-D scalar; on a circuit that scalar is
 * the arc length along the track centreline and the race distance is the
 * circumference. Only renderers consume this mapping — the authoritative
 * simulation never needs world coordinates.
 *
 * Anchoring (chosen so the straight track's conventions carry over):
 *   - Arc 0 is the start line at world origin (0, 0), heading +X.
 *   - The circle's centre sits at (0, R) where R = circumference / 2π,
 *     so the track curves toward +Z and a full lap returns to the start.
 *   - A lane's radial offset equals its straight-track Z offset: at the
 *     start line, `circuitPose(0, C, laneOffset).z === laneOffset`, which
 *     keeps lane assignment and avatar placement code shape-agnostic.
 *
 * Fairness note: every racer is measured by the same centreline arc
 * length — lanes are a visual offset only, exactly as on the straight
 * track where lane Z never affects the distance run. No staggered starts.
 */

import { LANE_WIDTH_M } from './RaceConstants'

/** World-space pose for an avatar / prop on the circuit. */
export interface CircuitPose {
  x: number
  z: number
  /**
   * Direction of travel as a rotation about +Y, in radians, measured
   * from +X toward +Z. 0 at the start line; grows monotonically with
   * arc length (one lap = 2π) so consumers can lerp without unwrapping.
   */
  headingRad: number
}

/** Centreline radius for a circuit of the given circumference. */
export function circuitRadiusM(circumferenceM: number): number {
  return circumferenceM / (2 * Math.PI)
}

/**
 * Signed centre offset of a lane from the track centreline — identical
 * to the straight track's lane-centre Z formula, centralised here so
 * circuit consumers don't re-derive it.
 */
export function laneCenterOffsetM(laneIndex: number, laneCount: number): number {
  return (laneIndex + 0.5) * LANE_WIDTH_M - (laneCount * LANE_WIDTH_M) / 2
}

/**
 * Map a centreline arc length to the world pose for a point offset
 * `lateralOffsetM` from the centreline (positive offsets sit toward the
 * circle's centre, mirroring the straight track's +Z lane direction at
 * the start line).
 */
export function circuitPose(
  arcLengthM: number,
  circumferenceM: number,
  lateralOffsetM = 0,
): CircuitPose {
  const radius = circuitRadiusM(circumferenceM)
  const theta = arcLengthM / radius
  const laneRadius = radius - lateralOffsetM
  return {
    x: laneRadius * Math.sin(theta),
    z: radius - laneRadius * Math.cos(theta),
    headingRad: theta,
  }
}
