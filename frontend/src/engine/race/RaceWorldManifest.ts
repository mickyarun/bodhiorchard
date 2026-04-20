// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * RaceWorldManifest — asset paths for the Kenney Racing Kit pieces used
 * by the race module.
 *
 * Source: https://kenney.nl/assets/racing-kit (CC0 1.0 Universal).
 * Only the subset we actually compose into the scene is listed here —
 * unused kit pieces (cars, corners, pits) are NOT copied into public/assets
 * to keep the bundle footprint minimal.
 *
 * Attribution: crediting Kenney is optional under CC0. We credit in
 * THIRD_PARTY_CREDITS.md and keep the Kenney License.txt alongside the
 * GLBs in public/assets/racing-kit/.
 */

const BASE = 'assets/racing-kit'
const GARDEN = 'assets/garden'

// Track surface is built procedurally in TrackBuilder — no GLBs.
// Decor pulls from two sources:
//   - Kenney Racing Kit (checker flags, overhead gantry) — racing-specific
//   - Garden kit (trees, bushes, rocks, grass clumps) — shared with dashboard
// Sharing garden assets keeps the race scene visually tied to the main world
// and avoids the "two separate aesthetics" feel.

// ─── Racing-kit decor (signage + race-specific props) ───────────────

export const DECOR_OVERHEAD = `${BASE}/overhead.glb`
export const DECOR_FLAG_CHECKERS = `${BASE}/flagCheckers.glb`
export const DECOR_TREE_LARGE = `${BASE}/treeLarge.glb`
export const DECOR_TREE_SMALL = `${BASE}/treeSmall.glb`

// ─── Garden-kit decor (denser natural ambience around the track) ────

export const DECOR_TREES: readonly string[] = [
  `${GARDEN}/tree_default.glb`,
  `${GARDEN}/tree_oak.glb`,
  `${GARDEN}/tree_fat.glb`,
  `${GARDEN}/tree_tall_green.glb`,
  `${GARDEN}/tree_leafy.glb`,
  `${GARDEN}/tree_round.glb`,
  `${GARDEN}/pine_tree.glb`,
]

export const DECOR_BUSHES: readonly string[] = [
  `${GARDEN}/bush_green.glb`,
  `${GARDEN}/bush_round.glb`,
  `${GARDEN}/bushes_cluster.glb`,
]

export const DECOR_ROCKS: readonly string[] = [
  `${GARDEN}/rock_smallA.glb`,
  `${GARDEN}/rock_smallB.glb`,
  `${GARDEN}/rock_largeA.glb`,
]

export const DECOR_GRASS: readonly string[] = [
  `${GARDEN}/grass.glb`,
  `${GARDEN}/grass_large.glb`,
  `${GARDEN}/grass_leafs.glb`,
]

export const DECOR_FLOWERS: readonly string[] = [
  `${GARDEN}/flower_redA.glb`,
  `${GARDEN}/flower_yellowA.glb`,
  `${GARDEN}/flower_purpleA.glb`,
]

/**
 * All paths the race decor builder may touch. Batch-loaded up front so
 * every GLB is resolved before scene composition starts.
 */
export const RACING_KIT_PATHS: readonly string[] = [
  DECOR_OVERHEAD,
  DECOR_FLAG_CHECKERS,
  DECOR_TREE_LARGE,
  DECOR_TREE_SMALL,
  ...DECOR_TREES,
  ...DECOR_BUSHES,
  ...DECOR_ROCKS,
  ...DECOR_GRASS,
  ...DECOR_FLOWERS,
]
