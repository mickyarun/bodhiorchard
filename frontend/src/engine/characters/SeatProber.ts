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
 * SeatProber — Detects furniture seat surface height via vertex geometry analysis.
 *
 * The hardcoded approach (50% of AABB height = seatY) fails because the AABB
 * includes the chair backrest, making 50% land somewhere on the back rather
 * than on the cushion top. This utility reads the actual mesh vertex data.
 *
 * Algorithm:
 *   1. Extract all vertex Y positions from every mesh in the furniture entity
 *   2. Transform them to wrapper-local space (Y=0 = floor, using world transforms)
 *   3. Build a 1cm-bin histogram of Y values
 *   4. Smooth with a 3-bin rolling average to suppress noise
 *   5. Find the peak bin in the "seat zone" (25–65% of total model height)
 *      — the seat cushion top has many coplanar vertices; legs and backrest are
 *        thinner and have lower vertex density per Y slice
 *   6. Return the top of that bin as the detected seat height
 *
 * Why not physics raycasting?
 * app.systems.rigidbody.raycastFirst() requires ammo.js (~2MB bundle cost) and
 * static RigidBodyComponents on every furniture entity. mesh.getPositions() gives
 * the same geometric result from the CPU-side vertex arrays PlayCanvas already
 * retains for GLB-loaded assets — no extra dependencies, no setup.
 *
 * World transforms work even before the building root is added to app.root:
 * PlayCanvas walks the parent chain, and an un-parented root treats its local
 * transform as the world transform. Furniture added to the root inherits this
 * correctly, so SeatProber is safe to call during building construction.
 *
 * Seat zone 25–65%:
 *   < 25%  — legs (thin, few vertices per Y slice)
 *   25–65% — seat cushion top (wide flat slab = many coplanar vertices)
 *   > 65%  — backrest (vertices present but fewer than a horizontal slab)
 */
import * as pc from 'playcanvas'

/** Y histogram resolution — 1cm bins give sub-centimetre accuracy. */
const BIN_SIZE = 0.01

/** Seat surface must be above this fraction of total model height. */
const SEAT_MIN_FRACTION = 0.25

/** Seat surface must be below this fraction of total model height. */
const SEAT_MAX_FRACTION = 0.65

/** Minimum vertex count in the peak bin to trust the detection. */
const MIN_PEAK_DENSITY = 5

export class SeatProber {
  /**
   * Detect the seat surface Y for a furniture entity.
   *
   * @param wrapper Entity returned by BuildingFactory.placeFurnitureCentered.
   *   Must be in the scene graph (or a detached sub-tree with a parented root)
   *   so that getWorldTransform() returns a valid transform chain.
   * @returns Detected seatY in wrapper-local space (0 = floor level),
   *   or null if detection fails (caller should fall back to SEAT_OFFSETS).
   */
  static probeSeatY(wrapper: pc.Entity): number | null {
    const wrapperWorldY = wrapper.getPosition().y
    const yValues: number[] = []
    const tempVec = new pc.Vec3()

    for (const rc of wrapper.findComponents('render') as pc.RenderComponent[]) {
      const worldMat = rc.entity.getWorldTransform()

      for (const mi of rc.meshInstances) {
        const positions: number[] = []
        mi.mesh.getPositions(positions)
        if (positions.length === 0) continue

        // Positions are [x0,y0,z0, x1,y1,z1, ...] in mesh-local space.
        // Transform each vertex to world space, then subtract wrapper world Y
        // to get wrapper-local Y. Y-axis rotation (yaw) does not affect the Y
        // component of transformed points, so this is valid for all orientations.
        for (let i = 0; i < positions.length; i += 3) {
          tempVec.set(positions[i], positions[i + 1], positions[i + 2])
          worldMat.transformPoint(tempVec, tempVec)
          const localY = tempVec.y - wrapperWorldY
          if (localY >= 0) yValues.push(localY)
        }
      }
    }

    if (yValues.length < MIN_PEAK_DENSITY) return null

    const maxY = Math.max(...yValues)
    if (maxY < 0.05) return null // too flat to be a chair

    // Build histogram
    const binCount = Math.ceil(maxY / BIN_SIZE) + 1
    const histogram = new Int32Array(binCount)
    for (const y of yValues) {
      const bin = Math.floor(y / BIN_SIZE)
      if (bin >= 0 && bin < binCount) histogram[bin]++
    }

    // 3-bin rolling average — suppresses single-vertex spikes
    const smoothed = new Float32Array(binCount)
    for (let b = 1; b < binCount - 1; b++) {
      smoothed[b] = (histogram[b - 1] + histogram[b] + histogram[b + 1]) / 3
    }

    // Find peak bin in seat zone
    const minBin = Math.floor(maxY * SEAT_MIN_FRACTION / BIN_SIZE)
    const maxBin = Math.min(
      Math.floor(maxY * SEAT_MAX_FRACTION / BIN_SIZE),
      binCount - 1,
    )

    let bestBin = -1
    let bestVal = 0
    for (let b = minBin; b <= maxBin; b++) {
      if (smoothed[b] > bestVal) {
        bestVal = smoothed[b]
        bestBin = b
      }
    }

    if (bestBin < 0 || bestVal < MIN_PEAK_DENSITY) return null

    // Top of the peak bin = seat surface top
    return (bestBin + 1) * BIN_SIZE
  }
}
