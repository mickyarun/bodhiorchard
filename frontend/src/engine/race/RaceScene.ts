// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * RaceScene — controller-less race scene driven entirely by per-build options.
 *
 * Build contract:
 *   scene.build(application, {
 *     distanceM,        // 100 or 200 (RaceRoom picks)
 *     racerCount,       // 2..10 (RaceRoom enforces bounds)
 *     cameraMode,       // 'participant' (rear chase) or 'spectator' (fixed overhead)
 *     racers: [{ id, name, config, laneIndex }...],
 *     leaderProvider,   // returns leader's current X in metres, driven by the client
 *   })
 *
 * The scene owns track / ground / finish arch / decor / avatars / camera and
 * tears them down in reverse order. It does NOT own physics — step 5's
 * `RaceRoomClient` calls `setRacerKinematics(id, x, v, sprinting)` each frame
 * based on the authoritative `RaceRoom` schema.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { KayKitCharacterFactory } from '../characters/KayKitCharacterFactory'
import type { CharacterConfig } from '../characters/CharacterConfig'
import { MIN_RACERS, MAX_RACERS, ALLOWED_DISTANCES_M, LANE_WIDTH_M } from '@shared/race/RaceConstants'
import { TrackBuilder } from './TrackBuilder'
import { FinishArch } from './FinishArch'
import { Ground } from './Ground'
import { DecorBuilder } from './DecorBuilder'
import { RacerAvatar } from './RacerAvatar'
import { RaceCamera } from './RaceCamera'
import { RaceCameraOverhead } from './RaceCameraOverhead'

export type RaceCameraMode = 'participant' | 'spectator'

export interface RaceSceneRacerSpec {
  /** Stable id — keys `setRacerKinematics` lookups. */
  id: string
  /** Display name shown in HUD + above the avatar. */
  name: string
  /** Visual config (legacy or KayKit) for the avatar. */
  config: CharacterConfig
  /** 0-based lane index within `racerCount` — picks the avatar's Z position. */
  laneIndex: number
}

export interface RaceSceneBuildOptions {
  distanceM: number
  racerCount: number
  cameraMode: RaceCameraMode
  racers: readonly RaceSceneRacerSpec[]
  /**
   * Called every frame by the participant camera to decide where to sit.
   * Return the leader's current X (metres). Safe to return 0 pre-countdown.
   * Ignored when `cameraMode === 'spectator'`.
   */
  leaderProvider: () => number
}

export class RaceScene {
  private loader: AssetLoader | null = null
  private factory: KayKitCharacterFactory | null = null
  private root: pc.Entity | null = null
  private track: TrackBuilder | null = null
  private arch: FinishArch | null = null
  private ground: Ground | null = null
  private decor: DecorBuilder | null = null
  private avatars: RacerAvatar[] = []
  private chaseCamera: RaceCamera | null = null
  private overheadCamera: RaceCameraOverhead | null = null
  private app: Application | null = null
  private updateHandler: ((dt: number) => void) | null = null

  async build(application: Application, opts: RaceSceneBuildOptions): Promise<void> {
    validateOptions(opts)

    const app = application.app
    this.loader = new AssetLoader(app)
    this.factory = new KayKitCharacterFactory(this.loader)

    this.root = new pc.Entity('RaceSceneRoot')
    application.root.addChild(this.root)

    // Track first — it reports lane-centre Zs that avatars rely on.
    this.track = new TrackBuilder(this.loader)
    const trackResult = await this.track.build(this.root, {
      distanceM: opts.distanceM,
      laneCount: opts.racerCount,
    })

    this.ground = new Ground(app)
    this.ground.build(this.root, {
      trackLengthM: trackResult.trackLengthM,
      trackWidthM: trackResult.tileWidthM,
    })

    this.arch = new FinishArch()
    this.arch.build(this.root, app.graphicsDevice, {
      xAtFinish: opts.distanceM,
      trackWidthM: trackResult.tileWidthM,
    })

    this.decor = new DecorBuilder(this.loader)
    await this.decor.build(this.root, { trackLengthM: trackResult.trackLengthM })

    await this.buildAvatars(opts.racers, trackResult.laneCenterZs)

    this.activateCamera(application, opts)

    // Drive per-frame avatar smoothing. Server patches set kinematic
    // targets at 20 Hz; the render loop interpolates between them so
    // motion stays visually continuous.
    this.app = application
    this.updateHandler = (dt: number) => {
      for (const a of this.avatars) a.update(dt)
    }
    application.app.on('update', this.updateHandler)
  }

  /**
   * Drive a racer's avatar from external physics state (step 5's
   * `RaceRoomClient`). No-op if the id isn't in the scene.
   */
  setRacerKinematics(racerId: string, positionM: number, velocityMps: number, isSprinting: boolean): void {
    for (const a of this.avatars) {
      if (a.racerId === racerId) {
        a.setKinematics(positionM, velocityMps, isSprinting)
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

  /** Look up a racer's smoothed display x by racer id. Returns 0 if unknown. */
  getRacerDisplayX(racerId: string): number {
    for (const a of this.avatars) if (a.racerId === racerId) return a.getDisplayX()
    return 0
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

    this.decor?.destroy()
    this.decor = null
    this.arch?.destroy()
    this.arch = null
    this.ground?.destroy()
    this.ground = null
    this.track?.destroy()
    this.track = null

    if (this.root) {
      this.root.destroy()
      this.root = null
    }

    this.factory = null
    this.loader = null
  }

  private async buildAvatars(racers: readonly RaceSceneRacerSpec[], laneCenterZs: readonly number[]): Promise<void> {
    if (!this.loader || !this.factory || !this.root) return

    for (const r of racers) {
      if (r.laneIndex < 0 || r.laneIndex >= laneCenterZs.length) {
        throw new Error(`RaceScene: laneIndex=${r.laneIndex} out of range for ${laneCenterZs.length} lanes`)
      }
      const avatar = new RacerAvatar(
        r.id,
        { name: r.name, config: r.config },
        laneCenterZs[r.laneIndex],
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

  private activateCamera(application: Application, opts: RaceSceneBuildOptions): void {
    if (opts.cameraMode === 'spectator') {
      this.overheadCamera = new RaceCameraOverhead(application.camera, {
        distanceM: opts.distanceM,
        trackWidthM: opts.racerCount * LANE_WIDTH_M,
      })
      this.overheadCamera.activate()
      return
    }

    this.chaseCamera = new RaceCamera(application.camera, application.app, opts.leaderProvider)
    this.chaseCamera.activate()
  }
}

function validateOptions(opts: RaceSceneBuildOptions): void {
  if (!ALLOWED_DISTANCES_M.includes(opts.distanceM as typeof ALLOWED_DISTANCES_M[number])) {
    throw new Error(`RaceScene: distanceM=${opts.distanceM} not in ${ALLOWED_DISTANCES_M.join('/')}`)
  }
  if (opts.racerCount < MIN_RACERS || opts.racerCount > MAX_RACERS) {
    throw new Error(`RaceScene: racerCount=${opts.racerCount} outside [${MIN_RACERS}..${MAX_RACERS}]`)
  }
  if (opts.racers.length !== opts.racerCount) {
    throw new Error(`RaceScene: racers.length=${opts.racers.length} must match racerCount=${opts.racerCount}`)
  }
}
