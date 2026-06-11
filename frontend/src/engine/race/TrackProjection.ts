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
 * TrackProjection — maps the physics' 1-D race scalar onto world space.
 *
 * The authoritative simulation only ever knows `positionM`, a scalar arc
 * length along the track centreline. Renderers (avatars, pads, hurdles,
 * checker bands, cameras) ask a TrackProjection where that scalar lives
 * in world space for a given lateral lane offset:
 *
 *   - StraightProjection: the original track — arc is world X, lateral
 *     offset is world Z, travel heading is constant +X.
 *   - CircuitProjection: wraps shared/race LoopPath — arc curves around
 *     an organic closed loop whose total length is the race distance.
 *     (CircuitGeometry's perfect circle remains as the convention
 *     reference; LoopPath shares its anchoring and lateral sign.)
 *
 * Keeping the mapping behind this interface means every placement site
 * is shape-agnostic; only RaceScene picks the implementation.
 */
import { loopPose } from '@shared/race/LoopPath'

/** Degrees per radian — CircuitGeometry speaks radians, PlayCanvas degrees. */
const DEG_PER_RAD = 180 / Math.PI

export interface TrackPose {
  x: number
  z: number
  /**
   * Travel direction about +Y in degrees: 0 = +X, growing toward +Z.
   * Monotonic across laps on a circuit (no 360° wrap) so consumers can
   * smooth/lerp it without unwrapping.
   */
  headingDeg: number
}

export interface TrackProjection {
  pose(arcLengthM: number, lateralOffsetM: number): TrackPose
}

/** The original straight track: arc = world X, lateral offset = world Z. */
export class StraightProjection implements TrackProjection {
  pose(arcLengthM: number, lateralOffsetM: number): TrackPose {
    return { x: arcLengthM, z: lateralOffsetM, headingDeg: 0 }
  }
}

/** One-lap closed loop — race distance is the loop's total length. */
export class CircuitProjection implements TrackProjection {
  constructor(private readonly circumferenceM: number) {}

  pose(arcLengthM: number, lateralOffsetM: number): TrackPose {
    const p = loopPose(arcLengthM, this.circumferenceM, lateralOffsetM)
    return { x: p.x, z: p.z, headingDeg: p.headingRad * DEG_PER_RAD }
  }
}

/**
 * Convert a travel heading into the PlayCanvas Y euler angle for an
 * entity whose long/forward geometry axis is local +X (track planes,
 * pad strips, hurdle bars, camera tangents).
 *
 * Sign derivation (verified empirically against pc.Quat —
 * `setFromEulerAngles(0, 90, 0)` maps +X → −Z and +Z → +X): PlayCanvas
 * +Y rotation is CCW looking down, turning +X toward −Z. Our heading
 * convention grows the opposite way (+X toward +Z), so the yaw is the
 * negated heading: yawDeg = −headingDeg. On the straight track heading
 * is always 0, so every existing yaw stays byte-identical.
 */
export function entityYawDeg(headingDeg: number): number {
  return -headingDeg
}
