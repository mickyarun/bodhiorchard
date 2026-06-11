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
 *   - circuit:  CircuitTrackBuilder loop drawn ONCE at the fixed
 *     LOOP_LENGTH_M (lap count comes from the race distance, not the loop
 *     size) + Ground sized to the loop's bounding box + FinishArch at the
 *     start line (which is also arc = LOOP_LENGTH_M — the start line's
 *     world pose, tangent +X, so the x-only FinishArch API needs no
 *     rotation) + a CircuitProjection over LOOP_LENGTH_M whose lap-wrap
 *     carries racers around the same loop once per lap. DecorBuilder is
 *     skipped on circuit — its prop scattering assumes a straight road
 *     edge — in favour of CircuitDecorBuilder's trackside village.
 *
 * Ownership: `destroy()` tears the pieces down in reverse build order,
 * mirroring RaceScene's convention. A failure mid-build cleans up the
 * already-built pieces before rethrowing so the caller never leaks
 * materials or meshes it has no handle to.
 */
import type * as pc from 'playcanvas'
import { loopBounds } from '@shared/race/LoopPath'
import { LOOP_LENGTH_M } from '@shared/race/RaceConstants'
import type { TrackShape } from '@shared/race/types'
import type { AssetLoader } from '../assets/AssetLoader'
import { TrackBuilder } from './TrackBuilder'
import { CircuitTrackBuilder } from './CircuitTrackBuilder'
import { FinishArch } from './FinishArch'
import { Ground } from './Ground'
import { DecorBuilder } from './DecorBuilder'
import { CircuitDecorBuilder } from './CircuitDecorBuilder'
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
  private circuitDecor: CircuitDecorBuilder | null = null
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
      // the X axis) — the circuit gets its own loop-aware treatment.
      this.decor = new DecorBuilder(loader)
      await this.decor.build(root, { trackLengthM: result.trackLengthM })
    } else {
      // Trackside village + cheering spectators, placed along the loop's
      // outer edge through loopPose. The loop is the fixed LOOP_LENGTH_M
      // regardless of lap count.
      this.circuitDecor = new CircuitDecorBuilder(loader)
      await this.circuitDecor.build(root, {
        circumferenceM: LOOP_LENGTH_M,
        trackWidthM: result.tileWidthM,
      })
    }

    // Pads + hurdles derive their arc positions from the same shared
    // module the server physics uses, so visuals and mechanics can't
    // drift. On the circuit they sit at fractions of the physical loop
    // (LOOP_LENGTH_M) — one set, seen once per lap; on the straight track
    // they span the whole distance.
    const featureLoopM = opts.trackShape === 'circuit' ? LOOP_LENGTH_M : opts.distanceM
    this.boostPads = new BoostPadBuilder()
    this.boostPads.build(root, {
      loopLengthM: featureLoopM,
      trackWidthM: result.tileWidthM,
      projection: this.projection,
    })
    this.hurdles = new HurdleBuilder()
    this.hurdles.build(root, {
      loopLengthM: featureLoopM,
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
    this.circuitDecor?.destroy()
    this.circuitDecor = null
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
    // The loop is drawn ONCE at the fixed LOOP_LENGTH_M — a 1-lap and a
    // 2-lap race share an identically-sized course. The projection wraps
    // arc lengths beyond the loop (the avatar's displayX climbs to the
    // race distance), so racers physically go around the same loop twice.
    this.projection = new CircuitProjection(LOOP_LENGTH_M)
    this.circuitTrack = new CircuitTrackBuilder()
    return this.circuitTrack.build(root, app.graphicsDevice, {
      circumferenceM: LOOP_LENGTH_M,
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
      // Footprint covering the loop's bounding box plus the road width,
      // centred on the box — the organic loop isn't symmetric about any
      // axis, so the old circle-radius framing no longer fits. Sized to
      // the fixed loop length, not the race distance.
      const bounds = loopBounds(LOOP_LENGTH_M)
      this.ground.build(root, {
        trackLengthM: bounds.maxX - bounds.minX + trackWidthM,
        trackWidthM: bounds.maxZ - bounds.minZ + trackWidthM,
        center: {
          x: (bounds.minX + bounds.maxX) / 2,
          z: (bounds.minZ + bounds.maxZ) / 2,
        },
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
    // Straight: the arch stands at x = distance. Circuit: the finish line
    // IS the start line — arc = LOOP_LENGTH_M wraps to the loop's start
    // world pose (origin, tangent +X, heading 360° ≡ 0°) — so the x-only,
    // unrotated FinishArch API places it exactly on the line, shared by
    // every lap.
    const finishPose = this.projection.pose(LOOP_LENGTH_M, 0)
    this.arch.build(root, app.graphicsDevice, {
      xAtFinish: opts.trackShape === 'circuit' ? finishPose.x : opts.distanceM,
      trackWidthM,
    })
  }
}
