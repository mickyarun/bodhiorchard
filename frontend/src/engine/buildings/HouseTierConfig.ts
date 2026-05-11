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
 * HouseTierConfig — Frontend-enriched tier record.
 *
 * Pure geometry (width, depth, doorIndex, bed, desk, unlockCost) lives in
 * `@shared/world/HouseTiers` and is the source of truth for both frontend
 * rendering and the multiplayer server. This file layers render-only fields
 * (name label, GLB paths, model scales, thumbnails) on top and re-exports
 * the legacy `HouseTierDef` / `getHouseTier` surface so existing consumers
 * need no import path changes.
 *
 * Adding a new tier: add its geometry entry to `shared/world/HouseTiers.ts`
 * AND its render entry here; both arrays must have the same tier numbers.
 */
import {
  HOUSE_TIER_GEOMETRIES,
  type HouseTierGeometry,
  getHouseTierGeometry,
} from '@shared/world/HouseTiers'

// Re-export shared constants so frontend callers have a single import root.
export {
  BED_SURFACE_Y,
  DESK_SEAT_Y,
  MAX_TIER_FOOTPRINT,
} from '@shared/world/HouseTiers'

/** Frontend render-only additions on top of the shared geometry record. */
export interface HouseTierDef extends HouseTierGeometry {
  name: string
  /** Preview thumbnail for the upgrade shop UI. Path relative to /public. */
  thumbnail: string
  /** If set, use this whole-building GLB instead of Kenney procedural walls+roof. */
  exteriorGlb?: string
  /** Fallback scale for KayKit exterior models (used only when AABB measurement fails). */
  exteriorScale?: number
  /** Fallback raw GLB footprint in world units before scaling (used only when measurement fails). */
  exteriorFootprint?: { w: number; d: number }
}

interface RenderFields {
  name: string
  thumbnail: string
  exteriorGlb?: string
  exteriorScale?: number
  exteriorFootprint?: { w: number; d: number }
}

/** Render-only fields keyed by tier — merged with shared geometry to produce the full record. */
const RENDER_BY_TIER: Record<number, RenderFields> = {
  1: {
    name: 'Hut',
    thumbnail: 'assets/buildings/kaykit/thumbnails/home_small.png',
    exteriorGlb: 'assets/buildings/kaykit/home_small.glb',
    exteriorScale: 2.0,
    exteriorFootprint: { w: 1.8, d: 1.8 },
  },
  2: {
    name: 'Cottage',
    thumbnail: 'assets/buildings/kaykit/thumbnails/home_medium.png',
    exteriorGlb: 'assets/buildings/kaykit/home_medium.glb',
    exteriorScale: 2.0,
    exteriorFootprint: { w: 2.2, d: 2.2 },
  },
  3: {
    name: 'Mansion',
    thumbnail: 'assets/buildings/kaykit/thumbnails/home_barracks.png',
    exteriorGlb: 'assets/buildings/kaykit/home_barracks.glb',
    exteriorScale: 1.8,
    exteriorFootprint: { w: 3.0, d: 3.0 },
  },
  4: {
    name: 'Villa',
    thumbnail: 'assets/buildings/kaykit/thumbnails/villa.png',
  },
}

export const HOUSE_TIERS: readonly HouseTierDef[] = HOUSE_TIER_GEOMETRIES.map(g => ({
  ...g,
  ...(RENDER_BY_TIER[g.tier] ?? { name: `Tier ${g.tier}`, thumbnail: '' }),
}))

export function getHouseTier(tier: number): HouseTierDef {
  const geometry = getHouseTierGeometry(tier)
  const render = RENDER_BY_TIER[geometry.tier] ?? { name: `Tier ${geometry.tier}`, thumbnail: '' }
  return { ...geometry, ...render }
}
