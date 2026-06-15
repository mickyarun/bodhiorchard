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
 * PostFX — CameraFrame post-processing for the garden camera.
 *
 * Wraps pc.CameraFrame (core engine, no extras needed): HDR render target
 * with subtle bloom, color grading, and vignette, settings from
 * Theme.POSTFX. SSAO/TAA/DOF stay off — they don't earn their cost in a
 * stylized low-poly scene.
 *
 * THE DOUBLE-TONE-MAP TRAP: Application.init sets ACES on the camera
 * component (correct when no post chain exists). When CameraFrame is
 * active it tone-maps inside its compose pass, so the camera's own
 * mapping must be NONE for the frame's lifetime — both active would
 * wash the scene gray. enable() performs the handoff; destroy()/
 * disable() restore camera ACES.
 *
 * Kill switch (no rebuild needed): `?nopostfx=1` or
 * `localStorage.setItem('garden:nopostfx', '1')` — a driver-specific
 * failure is one reload away from the plain pipeline.
 *
 * Lifecycle: created once per GardenEngine.init (the camera lives outside
 * the garden root and survives scene rebuilds); destroyed in
 * GardenEngine.destroy BEFORE app.destroy.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { Theme } from './Theme'

const STORAGE_KEY = 'garden:nopostfx'

export class PostFX {
  private frame: pc.CameraFrame | null = null
  private appRef: Application | null = null

  /** False when the user opted out via query param / localStorage. */
  static shouldEnable(): boolean {
    try {
      return !(
        new URLSearchParams(window.location.search).get('nopostfx') === '1' ||
        window.localStorage.getItem(STORAGE_KEY) === '1'
      )
    } catch {
      return true
    }
  }

  /** Build the frame chain and take over tone mapping from the camera. */
  enable(app: Application): void {
    if (this.frame) return
    this.appRef = app

    // Hand tone mapping to the post chain (see double-tone-map note above).
    app.setCameraToneMapping(pc.TONEMAP_NONE)

    const frame = new pc.CameraFrame(app.app, app.camera.camera!)
    frame.rendering.toneMapping = pc.TONEMAP_ACES
    frame.rendering.samples = 4  // MSAA — cheap AA for low-poly edges

    const fx = Theme.POSTFX
    frame.bloom.intensity = fx.bloomIntensity
    frame.grading.enabled = true
    frame.grading.saturation = fx.grading.saturation
    frame.grading.contrast = fx.grading.contrast
    frame.grading.brightness = fx.grading.brightness
    frame.vignette.intensity = fx.vignette.intensity
    frame.vignette.inner = fx.vignette.inner
    frame.vignette.outer = fx.vignette.outer
    frame.vignette.curvature = fx.vignette.curvature
    frame.update()

    this.frame = frame
  }

  /** Tear down the frame chain and give tone mapping back to the camera. */
  destroy(): void {
    if (!this.frame) return
    this.frame.destroy()
    this.frame = null
    this.appRef?.setCameraToneMapping(pc.TONEMAP_ACES)
    this.appRef = null
  }
}
