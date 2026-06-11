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
 * RaceSceneTrack — per-shape track assembly for RaceScene.
 *
 * Owns everything below the avatars: road surface, ground, finish arch,
 * decor, boost pads and hurdles. RaceScene stays a thin orchestrator
 * (avatars + cameras + kinematics) and under its size cap; the
 * straight/circuit branching lives here.
 *
 *   - straight: the original TrackBuilder / Ground / FinishArch /
 *     DecorBuilder path, untouched, with a StraightProjection.
 *   - circuit:  CircuitTrackBuilder ring + Ground sized to cover the
 *     full ring + FinishArch at arc = circumference (which is the start
 *     line's world pose, tangent +X, so the x-only FinishArch API needs
 *     no rotation) + a CircuitProjection. DecorBuilder is skipped for
 *     circuit v1 — its prop scattering assumes a straight road edge.
 *
 * Ownership: `destroy()` tears the pieces down in reverse build order,
 * mirroring RaceScene's convention. A failure mid-build cleans up the
 * already-built pieces before rethrowing so the caller never leaks
 * materials or meshes it has no handle to.
 */
import type * as pc from 'playcanvas'
import { circuitRadiusM } from '@shared/race/CircuitGeometry'
import type { TrackShape } from '@shared/race/types'
import type { AssetLoader } from '../assets/AssetLoader'
import { TrackBuilder } from './TrackBuilder'
import { CircuitTrackBuilder } from './CircuitTrackBuilder'
import { FinishArch } from './FinishArch'
import { Ground } from './Ground'
import { DecorBuilder } from './DecorBuilder'
import { BoostPadBuilder } from './BoostPadBuilder'
import { HurdleBuilder } from './HurdleBuilder'
import {
  CircuitProjection,
  StraightProjection,
  type TrackProjection,
} from './TrackProjection'

export interface TrackAssemblyOptions {
  /** Race distance in metres — straight length, or circuit circumference. */
  distanceM: number
  /** Lane count — one lane per racer. */
  racerCount: number
  /** Which layout to assemble. */
  trackShape: TrackShape
}

export interface TrackAssembly {
  /** Arc-length → world mapping for avatars, cameras and HUD consumers. */
  readonly projection: TrackProjection
  /**
   * Signed lateral offset of each lane centre from the track centreline,
   * indexed by lane. Numerically identical to the straight track's
   * historical `laneCenterZs` for both shapes.
   */
  readonly laneOffsetsM: readonly number[]
  /** Full road width — drives camera framing. */
  readonly trackWidthM: number
  /** Per-frame work (boost-pad emissive pulse). */
  update(dtSec: number): void
  /** Reverse-build-order teardown of every owned piece. */
  destroy(): void
}

export async function buildTrackAssembly(
  root: pc.Entity,
  app: pc.AppBase,
  loader: AssetLoader,
  opts: TrackAssemblyOptions,
): Promise<TrackAssembly> {
  const assembly = new TrackAssemblyImpl()
  try {
    await assembly.build(root, app, loader, opts)
    return assembly
  } catch (err) {
    assembly.destroy()
    throw err
  }
}

class TrackAssemblyImpl implements TrackAssembly {
  projection: TrackProjection = new StraightProjection()
  laneOffsetsM: readonly number[] = []
  trackWidthM = 0

  private straightTrack: TrackBuilder | null = null
  private circuitTrack: CircuitTrackBuilder | null = null
  private ground: Ground | null = null
  private arch: FinishArch | null = null
  private decor: DecorBuilder | null = null
  private boostPads: BoostPadBuilder | null = null
  private hurdles: HurdleBuilder | null = null

  async build(
    root: pc.Entity,
    app: pc.AppBase,
    loader: AssetLoader,
    opts: TrackAssemblyOptions,
  ): Promise<void> {
    // Road surface first — it reports the lane offsets avatars rely on.
    const result =
      opts.trackShape === 'circuit'
        ? this.buildCircuitSurface(root, app, opts)
        : await this.buildStraightSurface(root, loader, opts)
    this.laneOffsetsM = result.laneCenterZs
    this.trackWidthM = result.tileWidthM

    this.buildGround(root, app, opts, result.tileWidthM)
    this.buildFinishArch(root, app, opts, result.tileWidthM)

    if (opts.trackShape === 'straight') {
      // Decor assumes a straight road edge (props scattered along ±Z of
      // the X axis) — skipped on circuit until it learns the ring.
      this.decor = new DecorBuilder(loader)
      await this.decor.build(root, { trackLengthM: result.trackLengthM })
    }

    // Pads + hurdles derive their arc positions from the same shared
    // module the server physics uses, so visuals and mechanics can't
    // drift — and place themselves through the shape's projection.
    this.boostPads = new BoostPadBuilder()
    this.boostPads.build(root, {
      distanceM: opts.distanceM,
      trackWidthM: result.tileWidthM,
      projection: this.projection,
    })
    this.hurdles = new HurdleBuilder()
    this.hurdles.build(root, {
      distanceM: opts.distanceM,
      trackWidthM: result.tileWidthM,
      projection: this.projection,
    })
  }

  update(dtSec: number): void {
    this.boostPads?.update(dtSec)
  }

  destroy(): void {
    this.hurdles?.destroy()
    this.hurdles = null
    this.boostPads?.destroy()
    this.boostPads = null
    this.decor?.destroy()
    this.decor = null
    this.arch?.destroy()
    this.arch = null
    this.ground?.destroy()
    this.ground = null
    this.circuitTrack?.destroy()
    this.circuitTrack = null
    this.straightTrack?.destroy()
    this.straightTrack = null
  }

  private async buildStraightSurface(
    root: pc.Entity,
    loader: AssetLoader,
    opts: TrackAssemblyOptions,
  ): Promise<{ trackLengthM: number; tileWidthM: number; laneCenterZs: number[] }> {
    this.projection = new StraightProjection()
    this.straightTrack = new TrackBuilder(loader)
    return this.straightTrack.build(root, {
      distanceM: opts.distanceM,
      laneCount: opts.racerCount,
    })
  }

  private buildCircuitSurface(
    root: pc.Entity,
    app: pc.AppBase,
    opts: TrackAssemblyOptions,
  ): { trackLengthM: number; tileWidthM: number; laneCenterZs: number[] } {
    this.projection = new CircuitProjection(opts.distanceM)
    this.circuitTrack = new CircuitTrackBuilder()
    return this.circuitTrack.build(root, app.graphicsDevice, {
      circumferenceM: opts.distanceM,
      laneCount: opts.racerCount,
    })
  }

  private buildGround(
    root: pc.Entity,
    app: pc.AppBase,
    opts: TrackAssemblyOptions,
    trackWidthM: number,
  ): void {
    this.ground = new Ground(app)
    if (opts.trackShape === 'circuit') {
      // Square footprint covering the ring's outer edge, centred on the
      // circle centre (0, radius) per CircuitGeometry's anchoring.
      const radiusM = circuitRadiusM(opts.distanceM)
      const ringExtentM = 2 * radiusM + trackWidthM
      this.ground.build(root, {
        trackLengthM: ringExtentM,
        trackWidthM: ringExtentM,
        center: { x: 0, z: radiusM },
      })
      return
    }
    this.ground.build(root, { trackLengthM: opts.distanceM, trackWidthM })
  }

  private buildFinishArch(
    root: pc.Entity,
    app: pc.AppBase,
    opts: TrackAssemblyOptions,
    trackWidthM: number,
  ): void {
    this.arch = new FinishArch()
    // Straight: the arch stands at x = distance. Circuit: arc =
    // circumference wraps to the start line's world pose — origin,
    // tangent +X (heading 360° ≡ 0°) — so the x-only, unrotated
    // FinishArch API still places it exactly on the line.
    const finishPose = this.projection.pose(opts.distanceM, 0)
    this.arch.build(root, app.graphicsDevice, {
      xAtFinish: opts.trackShape === 'circuit' ? finishPose.x : opts.distanceM,
      trackWidthM,
    })
  }
}
