// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * PineTreeSystem — Tiered forest belt framing the hub world.
 *
 * Two density bands + species variation make the tree ring read as
 * "intentional forest" rather than "procedural scatter":
 *
 *   1. Framing clumps (inner band, r≈38): 3 dense clusters at angular
 *      positions BETWEEN the activity/habitation zones. These frame
 *      sightlines from the hub toward each zone and hide the transition
 *      between zone groups — the eye sees a tree wall, not empty grass.
 *
 *   2. Outer perimeter (r=55..85): uniform-ish scatter with 2 angular
 *      "gaps" where no trees are placed — suggests paths disappearing
 *      into the forest beyond, adding implied world-beyond depth.
 *
 * Species variation: pine (dominant), tall-green, leafy, autumn — mixed
 * so no single silhouette repeats in a cluster. Occasional autumn tree
 * gives warm color accents without a fall-biome commitment.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_PINES, FOREST_TREES } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'

// ─── Outer perimeter belt ────────────────────────────────────────────────
const OUTER_PINE_COUNT = 32
const OUTER_INNER_RADIUS = 55
const OUTER_OUTER_RADIUS = 85
const MIN_DISTANCE = 4.5

/** Angular gaps where no perimeter trees are placed — hints at "paths
 *  into the forest." Degrees in math convention (atan2(z,x)). */
const PERIMETER_GAPS_DEG: Array<{ center: number; halfWidth: number }> = [
  { center: 0,   halfWidth: 6 },   // due east
  { center: 180, halfWidth: 6 },   // due west
]

// ─── Inner framing clumps ────────────────────────────────────────────────
/**
 * Framing clumps sit BETWEEN the outer ring (r=55+) and the outer habitation
 * zones (housing/pool centers at r≈50). Placed at r=52 so they frame the
 * sightlines between zones without crowding the hub-adjacent area.
 */
const FRAMING_CLUMP_RADIUS = 52
const FRAMING_TREES_PER_CLUMP = 3     // tight trio reads as a single tree mass
const FRAMING_SPREAD = 3.5            // cluster blob half-width

/**
 * Angles chosen to sit between zone clusters in the current layout:
 *   -  90° = due south → between housing & pool (fills big southern gap)
 *   - 215° = NW → between coffee_bar and pavilion
 *   - 325° = NE → between pavilion and cafeteria
 */
const FRAMING_ANGLES_DEG = [90, 215, 325]

/**
 * Scale factor applied when species is NOT pine. The other GLBs in the
 * forest set (tree_tall_green, tree_autumn) have much larger default
 * bounds than pine_tree.glb — at pine's native scale they'd dwarf the
 * hub tree. 0.25 brings them into a pine-equivalent visual footprint.
 */
const NON_PINE_SCALE = 0.25

// ─── Species palette ──────────────────────────────────────────────────────
/**
 * Pine-dominant mix. `tree_leafy` deliberately excluded — its rounded
 * blob silhouette clashes visually with the pointy pine skyline and
 * reads as "wrong tree species" from the zoom-out camera. Keep the
 * leafy-blob look reserved for the hub anchor (tree_round) and the
 * repo trees, which are meant to be silhouette-distinct.
 */
const SPECIES_WEIGHTS: Array<{ pathIdx: number; weight: number }> = [
  { pathIdx: 0, weight: 0.70 },  // pine_tree (strongly dominant)
  { pathIdx: 1, weight: 0.20 },  // tree_tall_green
  { pathIdx: 2, weight: 0.10 },  // tree_autumn (rare warm accent)
]

export class PineTreeSystem {
  private root: pc.Entity | null = null

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('PineTreeSystem')

    // Load one of each species. Pine is the dominant choice; the others
    // provide silhouette variation. FOREST_TREES is already preloaded via
    // getEnvironmentGLBs() so these are warm-cache lookups.
    const speciesPaths = [
      SCATTER_PINES[0],               // pine_tree      (pathIdx 0)
      FOREST_TREES[2],                // tree_tall_green (pathIdx 1)
      FOREST_TREES[4],                // tree_autumn    (pathIdx 2)
    ]
    const assets = await loader.loadBatch(speciesPaths)

    // 1. Outer perimeter belt — uniform scatter with angular gaps
    const outerPoints = this.outerRingScatter(
      OUTER_PINE_COUNT, MIN_DISTANCE, exclusionZones,
    )
    for (const pt of outerPoints) {
      this.spawnTree(loader, assets, pt.x, pt.z, randRange(3, 7))
    }

    // 2. Inner framing clumps — dense clusters at between-zone angles
    for (const angleDeg of FRAMING_ANGLES_DEG) {
      this.spawnClump(loader, assets, angleDeg, exclusionZones)
    }

    app.root.addChild(this.root)
    return this.root
  }

  /** Spawn a single tree at (x,z) with random species, yaw, and scale. */
  private spawnTree(
    loader: AssetLoader,
    assets: pc.Asset[],
    x: number,
    z: number,
    scale: number,
  ): void {
    const speciesIdx = this.pickWeightedSpecies()
    const asset = assets[speciesIdx]
    const instance = loader.instance(asset)
    instance.setPosition(x, 0, z)
    instance.setLocalEulerAngles(0, randRange(0, 360), 0)
    // Non-pine GLBs (tall_green, autumn) have much larger default bounds
    // than pine — without the strong scale-down they dwarf the hub tree.
    const speciesScale = speciesIdx === 0 ? 1.0 : NON_PINE_SCALE
    const s = scale * speciesScale
    instance.setLocalScale(s, s, s)
    this.root!.addChild(instance)
  }

  /** Weighted random species index from SPECIES_WEIGHTS. */
  private pickWeightedSpecies(): number {
    const r = Math.random()
    let acc = 0
    for (const { pathIdx, weight } of SPECIES_WEIGHTS) {
      acc += weight
      if (r <= acc) return pathIdx
    }
    return SPECIES_WEIGHTS[0].pathIdx
  }

  /**
   * Perimeter ring scatter: uniform between INNER and OUTER, with angular
   * gaps (no trees in gap windows) that hint at forest paths beyond.
   */
  private outerRingScatter(
    count: number,
    minDist: number,
    exclusionZones: readonly ExclusionZone[],
  ): Array<{ x: number; z: number }> {
    const points: Array<{ x: number; z: number }> = []
    const maxAttempts = count * 20
    let attempts = 0

    while (points.length < count && attempts < maxAttempts) {
      attempts++
      const angleRad = Math.random() * Math.PI * 2
      const angleDeg = (angleRad * 180) / Math.PI
      if (this.isInGap(angleDeg)) continue

      const r = OUTER_INNER_RADIUS + Math.random() * (OUTER_OUTER_RADIUS - OUTER_INNER_RADIUS)
      const x = Math.cos(angleRad) * r
      const z = Math.sin(angleRad) * r

      if (isInsideAnyZone(x, z, exclusionZones)) continue
      if (this.isTooCloseToExisting(x, z, points, minDist)) continue
      points.push({ x, z })
    }
    return points
  }

  /**
   * Spawn FRAMING_TREES_PER_CLUMP trees in a jittered cluster at the given
   * angle. Each tree's position is the clump center + gaussian-ish jitter.
   * Clumps use denser-than-belt packing (smaller minDist) so silhouettes
   * overlap and read as a single "tree mass" rather than individual trees.
   */
  private spawnClump(
    loader: AssetLoader,
    assets: pc.Asset[],
    angleDeg: number,
    exclusionZones: readonly ExclusionZone[],
  ): void {
    const angleRad = (angleDeg * Math.PI) / 180
    const cx = Math.cos(angleRad) * FRAMING_CLUMP_RADIUS
    const cz = Math.sin(angleRad) * FRAMING_CLUMP_RADIUS

    const placed: Array<{ x: number; z: number }> = []
    let attempts = 0
    while (placed.length < FRAMING_TREES_PER_CLUMP && attempts < 40) {
      attempts++
      const x = cx + randRange(-FRAMING_SPREAD, FRAMING_SPREAD)
      const z = cz + randRange(-FRAMING_SPREAD, FRAMING_SPREAD)
      if (isInsideAnyZone(x, z, exclusionZones)) continue
      // Tighter min-distance inside a clump — trees are meant to clump.
      if (this.isTooCloseToExisting(x, z, placed, 2.2)) continue
      placed.push({ x, z })
      // Framing clumps sit slightly larger than the belt average to
      // stand out as sightline markers, but not so much they rival the
      // hub tree's visual weight.
      this.spawnTree(loader, assets, x, z, randRange(4, 6))
    }
  }

  private isInGap(angleDeg: number): boolean {
    const normalized = ((angleDeg % 360) + 360) % 360
    for (const gap of PERIMETER_GAPS_DEG) {
      const center = ((gap.center % 360) + 360) % 360
      const diff = Math.min(
        Math.abs(normalized - center),
        360 - Math.abs(normalized - center),
      )
      if (diff < gap.halfWidth) return true
    }
    return false
  }

  private isTooCloseToExisting(
    x: number, z: number,
    points: Array<{ x: number; z: number }>,
    minDist: number,
  ): boolean {
    const minSq = minDist * minDist
    for (const p of points) {
      const dx = x - p.x
      const dz = z - p.z
      if (dx * dx + dz * dz < minSq) return true
    }
    return false
  }

  destroy(): void {
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
