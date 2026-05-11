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
 * RaceEngine — race scene bootstrap.
 *
 * Thin wrapper: creates a canvas + PlayCanvas application, asks the scene
 * to build itself from per-room options (distance, racer count, camera
 * mode, racer specs, leader provider), and tears everything down on
 * destroy. Step 5's `RaceRoomClient` will construct the options from the
 * `RaceRoom` schema and keep the scene in sync each frame.
 */
import { Application } from '../core/Application'
import { RaceScene, type RaceSceneBuildOptions } from './RaceScene'
import { PerfStats, shouldEnableStats } from './PerfStats'
import type { RaceHudState } from './types'

export interface RaceEngineInitOptions {
  width: number
  height: number
  scene: RaceSceneBuildOptions
}

export class RaceEngine {
  private application: Application | null = null
  private scene: RaceScene | null = null
  private canvas: HTMLCanvasElement | null = null
  private stats: PerfStats | null = null

  async init(container: HTMLElement, opts: RaceEngineInitOptions): Promise<void> {
    this.canvas = document.createElement('canvas')
    Object.assign(this.canvas.style, { width: '100%', height: '100%', display: 'block' })
    container.appendChild(this.canvas)

    this.application = new Application()
    this.application.init(this.canvas, opts.width, opts.height)

    this.scene = new RaceScene()
    try {
      await this.scene.build(this.application, opts.scene)
    } catch (err) {
      this.destroy()
      throw err
    }

    if (shouldEnableStats()) {
      this.stats = new PerfStats(this.application.app)
      this.stats.enable()
    }
  }

  /** Drive a racer's avatar from client-side physics state. */
  setRacerKinematics(racerId: string, positionM: number, velocityMps: number, isSprinting: boolean): void {
    this.scene?.setRacerKinematics(racerId, positionM, velocityMps, isSprinting)
  }

  /** Flip a racer's finished flag — plays the Cheer emote on entry. */
  setRacerFinished(racerId: string, finished: boolean): void {
    this.scene?.setRacerFinished(racerId, finished)
  }

  /** Get the smoothed on-screen x of a specific racer — used to keep the
   *  participant camera glued to the local player's avatar. */
  getRacerDisplayX(racerId: string): number {
    return this.scene?.getRacerDisplayX(racerId) ?? 0
  }

  resize(width: number, height: number): void {
    this.application?.resize(width, height)
  }

  /**
   * HUD state is repopulated by Step 5 once `RaceRoomClient` is wired.
   * For now returns null.
   */
  getHudState(): RaceHudState | null {
    return null
  }

  destroy(): void {
    this.stats?.destroy()
    this.stats = null
    this.scene?.destroy()
    this.scene = null
    this.application?.destroy()
    this.application = null
    if (this.canvas?.parentElement) {
      this.canvas.parentElement.removeChild(this.canvas)
    }
    this.canvas = null
  }
}

export type { RaceSceneBuildOptions, RaceSceneRacerSpec, RaceCameraMode } from './RaceScene'
export type {
  RacePhase,
  Placing,
  RaceHudState,
  RaceHudSlot,
} from './types'
