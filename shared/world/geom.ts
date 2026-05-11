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
 * Pure 2D geometry helpers for the xz plane (PlayCanvas world, y-up).
 *
 * Imported by both the frontend engine and the multiplayer server. Keep
 * platform-free: no PlayCanvas, no Node, no browser APIs.
 */

/**
 * Rotate a point in the xz plane around a pivot by `yawRad` radians.
 *
 * Sign convention matches PlayCanvas entity yaw: positive `yawRad`
 * rotates counter-clockwise when viewed from above (looking down -Y).
 * That mirrors `entity.setLocalEulerAngles(0, yawDeg, 0)`, so the
 * helper composes correctly with visual rotation on both sides.
 */
export function rotatePointAroundPivot(
  lx: number, lz: number,
  yawRad: number,
  cx: number, cz: number,
): { x: number; z: number } {
  const dx = lx - cx
  const dz = lz - cz
  const cos = Math.cos(yawRad)
  const sin = Math.sin(yawRad)
  return {
    x: cx + dx * cos + dz * sin,
    z: cz - dx * sin + dz * cos,
  }
}

/**
 * Convert a point from a house-local frame to world space using its
 * composed pivot (x, z are world; yawDeg is the composed rotation of
 * house-yaw + parent-zone-yaw).
 *
 * This is the single read path for anything that used to mutate
 * HouseResult.seats / bedPosition / exitPosition into world coordinates.
 */
export function toWorld(
  local: { x: number; z: number },
  pivot: { x: number; z: number; yawDeg: number },
): { x: number; z: number } {
  const yawRad = (pivot.yawDeg * Math.PI) / 180
  const cos = Math.cos(yawRad)
  const sin = Math.sin(yawRad)
  return {
    x: pivot.x + local.x * cos + local.z * sin,
    z: pivot.z - local.x * sin + local.z * cos,
  }
}
