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
 * DecorBuilder — dense, layered environment around the straight track.
 *
 * The scene reads as "alive" only when there's texture at every distance:
 *   - Foreground (0–3 m off the edge): grass clumps, small flowers,
 *     racing-kit checker flags as lane markers every ~20 m.
 *   - Middle ground (3–10 m): bushes + rocks, breaking up silhouettes.
 *   - Background (10–25 m): trees in two staggered rows so the horizon
 *     doesn't feel like a postage-stamp row of popsicle-shaped pines.
 *
 * All scattering is deterministic — keyed off (index × prime) mod N — so
 * repeated scene mounts produce identical layouts. That matters for the
 * spectator camera: the finish arch lines up at x = distanceM every time.
 *
 * Ownership:
 *   - Owns one wrapper entity that parents every decor piece.
 *   - Borrows GLBs from the shared AssetLoader — does NOT destroy them.
 *   - destroy() cascades entity.destroy() through the wrapper.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import {
  DECOR_FLAG_CHECKERS,
  DECOR_TREES,
  DECOR_BUSHES,
  DECOR_ROCKS,
  DECOR_GRASS,
  DECOR_FLOWERS,
} from './RaceWorldManifest'
import { disposeEntity } from './dispose'

/** Yaw applied to GLBs so "front" roughly faces the track. */
const DECOR_YAW_DEG = 90

/** Per-axis offsets where each decor layer lives, measured from track centre. */
const FOREGROUND_Z = 3.5    // grass + flowers + checker flags
const MIDGROUND_Z_MIN = 5
const MIDGROUND_Z_MAX = 10
const BACKGROUND_Z_MIN = 12
const BACKGROUND_Z_MAX = 22

/** Density knobs — tuned for 100 m track; scale with distanceM. */
const TREES_PER_10M = 4
const BUSHES_PER_10M = 3
const ROCKS_PER_10M = 1.2
const GRASS_PER_10M = 8
const FLAG_SPACING_M = 20

export interface DecorBuildOptions {
  trackLengthM: number
}

/**
 * Seeded pseudo-random generator. We want deterministic scatter so the
 * layout is identical across mounts but feels random. Index → [0, 1).
 */
function hash01(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453
  return x - Math.floor(x)
}
function range(seed: number, min: number, max: number): number {
  return min + hash01(seed) * (max - min)
}
function signed(seed: number): number { return hash01(seed) * 2 - 1 }

export class DecorBuilder {
  private loader: AssetLoader
  private root: pc.Entity | null = null

  constructor(loader: AssetLoader) {
    this.loader = loader
  }

  async build(parent: pc.Entity, opts: DecorBuildOptions): Promise<void> {
    // All decor loads in parallel so the scene build isn't bottlenecked
    // on any single asset. `AssetLoader.loadBatch` dedupes already-cached
    // entries, so re-mounting is cheap.
    const [flagChecker, ...others] = await Promise.all([
      this.loader.load(DECOR_FLAG_CHECKERS),
      Promise.all(DECOR_TREES.map(p => this.loader.load(p))),
      Promise.all(DECOR_BUSHES.map(p => this.loader.load(p))),
      Promise.all(DECOR_ROCKS.map(p => this.loader.load(p))),
      Promise.all(DECOR_GRASS.map(p => this.loader.load(p))),
      Promise.all(DECOR_FLOWERS.map(p => this.loader.load(p))),
    ])
    const [trees, bushes, rocks, grass, flowers] = others as pc.Asset[][]

    this.root = new pc.Entity('RaceDecor')
    parent.addChild(this.root)

    const { trackLengthM } = opts

    this.scatterTrees(trees, trackLengthM)
    this.scatterBushes(bushes, trackLengthM)
    this.scatterRocks(rocks, trackLengthM)
    this.scatterGrass(grass, trackLengthM)
    this.scatterFlowers(flowers, trackLengthM)
    this.placeFlagMarkers(flagChecker, trackLengthM)
  }

  destroy(): void {
    disposeEntity(this.root)
    this.root = null
  }

  /** Two staggered rows of trees per side — breaks up the flat horizon. */
  private scatterTrees(trees: pc.Asset[], trackLengthM: number): void {
    // Extend 20% past the finish line so trees frame the arch from both
    // approach and beyond — otherwise the world ends abruptly at x=distanceM.
    const spanStart = -trackLengthM * 0.15
    const spanEnd = trackLengthM * 1.15
    const span = spanEnd - spanStart
    const count = Math.max(8, Math.round(TREES_PER_10M * (span / 10)))

    for (let i = 0; i < count; i++) {
      const asset = trees[Math.floor(hash01(i * 31) * trees.length)]
      const x = spanStart + range(i * 17, 0, span)
      const side = i % 2 === 0 ? -1 : 1
      const inner = i % 3 === 0
      const zAbs = inner
        ? range(i * 47, BACKGROUND_Z_MIN, BACKGROUND_Z_MIN + 4)
        : range(i * 53, BACKGROUND_Z_MIN + 4, BACKGROUND_Z_MAX)
      const z = side * zAbs
      const scale = range(i * 67, 0.85, 1.35)
      const yaw = hash01(i * 71) * 360
      this.place(asset, x, z, yaw, scale)
    }
  }

  /** Bushes + rocks fill the gap between foreground and trees. */
  private scatterBushes(bushes: pc.Asset[], trackLengthM: number): void {
    const count = Math.max(6, Math.round(BUSHES_PER_10M * (trackLengthM / 10) * 2))
    for (let i = 0; i < count; i++) {
      const asset = bushes[Math.floor(hash01(i * 29) * bushes.length)]
      const x = range(i * 19, -trackLengthM * 0.1, trackLengthM * 1.1)
      const side = i % 2 === 0 ? -1 : 1
      const z = side * range(i * 41, MIDGROUND_Z_MIN, MIDGROUND_Z_MAX)
      const scale = range(i * 59, 0.7, 1.1)
      this.place(asset, x, z, hash01(i * 73) * 360, scale)
    }
  }

  private scatterRocks(rocks: pc.Asset[], trackLengthM: number): void {
    const count = Math.max(4, Math.round(ROCKS_PER_10M * (trackLengthM / 10) * 2))
    for (let i = 0; i < count; i++) {
      const asset = rocks[Math.floor(hash01(i * 83) * rocks.length)]
      const x = range(i * 23, -trackLengthM * 0.05, trackLengthM * 1.05)
      const side = i % 2 === 0 ? -1 : 1
      const z = side * range(i * 37, MIDGROUND_Z_MIN + 1, MIDGROUND_Z_MAX - 1)
      const scale = range(i * 89, 0.6, 1.15)
      this.place(asset, x, z, hash01(i * 97) * 360, scale)
    }
  }

  /** Grass clumps hug the track edge and soften the sand/grass boundary. */
  private scatterGrass(grass: pc.Asset[], trackLengthM: number): void {
    const count = Math.max(10, Math.round(GRASS_PER_10M * (trackLengthM / 10) * 2))
    for (let i = 0; i < count; i++) {
      const asset = grass[Math.floor(hash01(i * 11) * grass.length)]
      const x = range(i * 7, -trackLengthM * 0.05, trackLengthM * 1.05)
      const side = i % 2 === 0 ? -1 : 1
      // Closer to the track than bushes/rocks — sits right at the edge.
      const z = side * range(i * 13, FOREGROUND_Z, FOREGROUND_Z + 2)
      const scale = range(i * 61, 0.6, 1.0)
      this.place(asset, x, z, hash01(i * 79) * 360, scale)
    }
  }

  /** Pops of colour — small flower clumps interleaved with the grass. */
  private scatterFlowers(flowers: pc.Asset[], trackLengthM: number): void {
    const count = Math.max(6, Math.round(2 * (trackLengthM / 10) * 2))
    for (let i = 0; i < count; i++) {
      const asset = flowers[Math.floor(hash01(i * 101) * flowers.length)]
      const x = range(i * 103, 0, trackLengthM)
      const side = (i + 1) % 2 === 0 ? -1 : 1
      const z = side * (FOREGROUND_Z + signed(i * 107) * 0.6)
      this.place(asset, x, z, hash01(i * 109) * 360, 0.9)
    }
  }

  /**
   * Checker flags planted at regular intervals along both sides of the
   * track. They read as "race markers" from the overhead camera and
   * give chase-cam racers a visual tempo as they pass each one.
   */
  private placeFlagMarkers(flagAsset: pc.Asset, trackLengthM: number): void {
    const trackEdgeZ = FOREGROUND_Z - 1.5  // just outside the painted edge
    for (let x = FLAG_SPACING_M; x < trackLengthM; x += FLAG_SPACING_M) {
      this.place(flagAsset, x, -trackEdgeZ, DECOR_YAW_DEG + 180, 1)
      this.place(flagAsset, x, +trackEdgeZ, DECOR_YAW_DEG, 1)
    }
  }

  private place(asset: pc.Asset, x: number, z: number, yawDeg: number, scale: number = 1): pc.Entity {
    const entity = this.loader.instance(asset)
    entity.setLocalPosition(x, 0, z)
    entity.setLocalEulerAngles(0, yawDeg, 0)
    if (scale !== 1) entity.setLocalScale(scale, scale, scale)
    this.root!.addChild(entity)
    return entity
  }
}
