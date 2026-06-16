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
 * RaceScene — controller-less race scene driven entirely by per-build options.
 *
 * Build contract:
 *   scene.build(application, {
 *     distanceM,        // 100 or 200 (RaceRoom picks)
 *     racerCount,       // 2..10 (RaceRoom enforces bounds)
 *     trackShape,       // 'straight' (default) or 'circuit' (one lap)
 *     cameraMode,       // 'participant' (rear chase) or 'spectator' (fixed overhead)
 *     racers: [{ id, name, config, laneIndex }...],
 *     leaderProvider,   // returns the tracked racer's arc length in metres
 *   })
 *
 * Track / ground / arch / decor / pads / hurdles live in the
 * TrackAssembly (RaceSceneTrack.ts) — this file owns avatars, cameras
 * and the kinematics bridge, and tears everything down in reverse
 * order. It does NOT own physics — the live panel calls
 * `setRacerKinematics(id, kinematics)` each frame with state derived
 * from the authoritative `RaceRoom` schema; positionM stays a 1-D arc
 * scalar that the assembly's TrackProjection maps to world space.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { KayKitCharacterFactory } from '../characters/KayKitCharacterFactory'
import type { CharacterConfig } from '../characters/CharacterConfig'
import {
  MIN_RACERS,
  MAX_RACERS,
  ALLOWED_DISTANCES_M,
  ALLOWED_TRACK_SHAPES,
  LOOP_LENGTH_M,
} from '@shared/race/RaceConstants'
import { loopBounds } from '@shared/race/LoopPath'
import type { TrackShape } from '@shared/race/types'
import { buildTrackAssembly, type TrackAssembly } from './RaceSceneTrack'
import { RacerAvatar } from './RacerAvatar'
import { RaceCamera } from './RaceCamera'
import { RaceCameraOverhead, type PackFraming } from './RaceCameraOverhead'
import type { RacerKinematics } from './types'

export type RaceCameraMode = 'participant' | 'spectator'

export interface RaceSceneRacerSpec {
  /** Stable id — keys `setRacerKinematics` lookups. */
  id: string
  /** Display name shown in HUD + above the avatar. */
  name: string
  /** Visual config (legacy or KayKit) for the avatar. */
  config: CharacterConfig
  /** 0-based lane index within `racerCount` — picks the avatar's lane offset. */
  laneIndex: number
}

export interface RaceSceneBuildOptions {
  distanceM: number
  racerCount: number
  /**
   * Track layout. Optional with a 'straight' default so pre-circuit
   * callers (and rooms created by older servers) keep working unchanged.
   */
  trackShape?: TrackShape
  cameraMode: RaceCameraMode
  racers: readonly RaceSceneRacerSpec[]
  /**
   * Called every frame by the participant camera to decide where to sit.
   * Return the tracked racer's current arc length (metres) — world X on
   * the straight track. Safe to return 0 pre-countdown. Ignored when
   * `cameraMode === 'spectator'`.
   */
  leaderProvider: () => number
}

export class RaceScene {
  private loader: AssetLoader | null = null
  private factory: KayKitCharacterFactory | null = null
  private root: pc.Entity | null = null
  private assembly: TrackAssembly | null = null
  private avatars: RacerAvatar[] = []
  private chaseCamera: RaceCamera | null = null
  private overheadCamera: RaceCameraOverhead | null = null
  private app: Application | null = null
  private updateHandler: ((dt: number) => void) | null = null

  async build(application: Application, opts: RaceSceneBuildOptions): Promise<void> {
    validateOptions(opts)
    const trackShape: TrackShape = opts.trackShape ?? 'straight'

    const app = application.app
    this.loader = new AssetLoader(app)
    this.factory = new KayKitCharacterFactory(this.loader)

    this.root = new pc.Entity('RaceSceneRoot')
    application.root.addChild(this.root)

    // Track first — it reports the lane offsets avatars rely on, and the
    // projection every placement site shares.
    this.assembly = await buildTrackAssembly(this.root, app, this.loader, {
      distanceM: opts.distanceM,
      racerCount: opts.racerCount,
      trackShape,
    })

    await this.buildAvatars(opts.racers, this.assembly)

    this.activateCamera(application, opts, trackShape)

    // Drive per-frame avatar smoothing. Server patches set kinematic
    // targets at 20 Hz; the render loop interpolates between them so
    // motion stays visually continuous.
    this.app = application
    this.updateHandler = (dt: number) => {
      for (const a of this.avatars) a.update(dt)
      this.assembly?.update(dt)
    }
    application.app.on('update', this.updateHandler)
  }

  /**
   * Drive a racer's avatar from external physics state (step 5's
   * `RaceRoomClient`). No-op if the id isn't in the scene.
   */
  setRacerKinematics(racerId: string, kinematics: RacerKinematics): void {
    for (const a of this.avatars) {
      if (a.racerId === racerId) {
        a.setKinematics(kinematics)
        return
      }
    }
  }

  /** Flip a racer's finished flag — triggers the Cheer emote on entry. */
  setRacerFinished(racerId: string, finished: boolean): void {
    for (const a of this.avatars) {
      if (a.racerId === racerId) {
        a.setFinished(finished)
        return
      }
    }
  }

  getAvatars(): readonly RacerAvatar[] {
    return this.avatars
  }

  /** Look up a racer's smoothed display arc length by racer id. Returns 0 if unknown. */
  getRacerDisplayX(racerId: string): number {
    for (const a of this.avatars) if (a.racerId === racerId) return a.getDisplayX()
    return 0
  }

  /**
   * Bounding box of every racer's current world position, as a centre + the
   * larger XZ spread — what the spectator camera frames each frame. Null before
   * any avatars exist (the camera falls back to the course centre).
   */
  private computePackFraming(): PackFraming | null {
    if (this.avatars.length === 0) return null
    let minX = Infinity
    let maxX = -Infinity
    let minZ = Infinity
    let maxZ = -Infinity
    for (const a of this.avatars) {
      const p = a.getGroundXZ()
      if (p.x < minX) minX = p.x
      if (p.x > maxX) maxX = p.x
      if (p.z < minZ) minZ = p.z
      if (p.z > maxZ) maxZ = p.z
    }
    return {
      x: (minX + maxX) / 2,
      z: (minZ + maxZ) / 2,
      spreadM: Math.max(maxX - minX, maxZ - minZ),
    }
  }

  /** Centre of the course — the spectator camera's pre-race fallback target. */
  private courseCenter(trackShape: TrackShape, distanceM: number): { x: number; z: number } {
    if (trackShape === 'circuit') {
      const b = loopBounds(LOOP_LENGTH_M)
      return { x: (b.minX + b.maxX) / 2, z: (b.minZ + b.maxZ) / 2 }
    }
    return { x: distanceM / 2, z: 0 }
  }

  destroy(): void {
    // Reverse-order teardown mirrors the build order so dependents disappear
    // before their dependencies.
    if (this.updateHandler && this.app) {
      this.app.app.off('update', this.updateHandler)
    }
    this.updateHandler = null
    this.app = null

    this.chaseCamera?.destroy()
    this.chaseCamera = null
    this.overheadCamera?.destroy()
    this.overheadCamera = null

    for (const a of this.avatars) a.destroy()
    this.avatars = []

    this.assembly?.destroy()
    this.assembly = null

    if (this.root) {
      this.root.destroy()
      this.root = null
    }

    this.factory = null
    this.loader = null
  }

  private async buildAvatars(
    racers: readonly RaceSceneRacerSpec[],
    assembly: TrackAssembly,
  ): Promise<void> {
    if (!this.loader || !this.factory || !this.root) return

    const laneOffsets = assembly.laneOffsetsM
    for (const r of racers) {
      if (r.laneIndex < 0 || r.laneIndex >= laneOffsets.length) {
        throw new Error(`RaceScene: laneIndex=${r.laneIndex} out of range for ${laneOffsets.length} lanes`)
      }
      const avatar = new RacerAvatar(
        r.id,
        { name: r.name, config: r.config },
        { laneOffsetM: laneOffsets[r.laneIndex], projection: assembly.projection },
        { loader: this.loader, characters: this.factory },
      )
      try {
        await avatar.build(this.root)
        this.avatars.push(avatar)
      } catch (err) {
        // Partially built avatars clean up after themselves; bail out of
        // the whole scene build so the caller's try/catch can tear down.
        avatar.destroy()
        throw err
      }
    }
  }

  private activateCamera(
    application: Application,
    opts: RaceSceneBuildOptions,
    trackShape: TrackShape,
  ): void {
    if (opts.cameraMode === 'spectator') {
      this.overheadCamera = new RaceCameraOverhead(application.camera, application.app, {
        framingProvider: () => this.computePackFraming(),
        fallbackCenter: this.courseCenter(trackShape, opts.distanceM),
      })
      this.overheadCamera.activate()
      return
    }

    // The chase camera consumes centreline poses (position + travel
    // heading): the panel's leaderProvider keeps returning the 1-D arc
    // scalar and the shape's projection turns it into world space here.
    this.chaseCamera = new RaceCamera(application.camera, application.app, () =>
      this.assembly!.projection.pose(opts.leaderProvider(), 0),
    )
    this.chaseCamera.activate()
  }
}

function validateOptions(opts: RaceSceneBuildOptions): void {
  if (!ALLOWED_DISTANCES_M.includes(opts.distanceM as typeof ALLOWED_DISTANCES_M[number])) {
    throw new Error(`RaceScene: distanceM=${opts.distanceM} not in ${ALLOWED_DISTANCES_M.join('/')}`)
  }
  if (
    opts.trackShape !== undefined &&
    !(ALLOWED_TRACK_SHAPES as readonly string[]).includes(opts.trackShape)
  ) {
    throw new Error(
      `RaceScene: trackShape=${opts.trackShape} not in ${ALLOWED_TRACK_SHAPES.join('/')}`,
    )
  }
  if (opts.racerCount < MIN_RACERS || opts.racerCount > MAX_RACERS) {
    throw new Error(`RaceScene: racerCount=${opts.racerCount} outside [${MIN_RACERS}..${MAX_RACERS}]`)
  }
  if (opts.racers.length !== opts.racerCount) {
    throw new Error(`RaceScene: racers.length=${opts.racers.length} must match racerCount=${opts.racerCount}`)
  }
}
