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
 * PerfHud — dev-only on-screen performance readout for the garden engine.
 *
 * Shows total draw calls (forward + shadow passes), FPS, and frame time,
 * sampled from `app.stats`. PlayCanvas's production build fills
 * `stats.drawCalls.total` and `stats.frame.fps` every frame via
 * `_fillFrameStatsBasic` — no profiler build needed. Detailed stats
 * (triangles, forward/shadow split) only exist in the debug/profiler
 * builds, so they're shown when non-zero and omitted otherwise.
 *
 * Activation is opt-in even in dev, so the HUD never skews measurements
 * for someone who didn't ask for it:
 *   - URL:          ?perf=1
 *   - localStorage: localStorage.setItem('garden:perfhud', '1')
 *
 * The DOM node updates at most every 500 ms — per-frame work is a handful
 * of float reads, so attaching the HUD does not perturb what it measures.
 */
import type * as pc from 'playcanvas'

const UPDATE_INTERVAL_S = 0.5
const STORAGE_KEY = 'garden:perfhud'

export class PerfHud {
  private el: HTMLDivElement | null = null
  private sinceUpdate = 0
  private fpsEma = 0

  /** True when the HUD should be created for this session (dev + opt-in). */
  static shouldEnable(): boolean {
    if (!import.meta.env.DEV) return false
    try {
      return (
        new URLSearchParams(window.location.search).get('perf') === '1' ||
        window.localStorage.getItem(STORAGE_KEY) === '1'
      )
    } catch {
      return false
    }
  }

  /**
   * Start sampling `app` and rendering the overlay into `container`.
   * Returns a detach function that removes the listener and the DOM node.
   */
  attach(app: pc.AppBase, container: HTMLElement): () => void {
    this.el = document.createElement('div')
    this.el.style.cssText = [
      'position:absolute', 'top:8px', 'left:8px', 'z-index:50',
      'padding:6px 10px', 'border-radius:6px',
      'background:rgba(10,14,10,0.72)', 'color:#c8f0c8',
      'font:11px/1.5 ui-monospace,monospace', 'pointer-events:none',
      'white-space:pre',
    ].join(';')
    this.el.textContent = 'perf: sampling…'
    container.appendChild(this.el)

    const onUpdate = (dt: number): void => this.sample(app, dt)
    app.on('update', onUpdate)

    return () => {
      app.off('update', onUpdate)
      this.el?.remove()
      this.el = null
    }
  }

  private sample(app: pc.AppBase, dt: number): void {
    if (dt > 0) {
      const fps = 1 / dt
      this.fpsEma = this.fpsEma === 0 ? fps : this.fpsEma * 0.95 + fps * 0.05
    }

    this.sinceUpdate += dt
    if (this.sinceUpdate < UPDATE_INTERVAL_S || !this.el) return
    this.sinceUpdate = 0

    const stats = (app as unknown as {
      stats: {
        frame: { ms: number; triangles: number }
        drawCalls: { total: number }
      }
    }).stats

    const lines = [
      `draws ${stats.drawCalls.total}`,
      `fps   ${this.fpsEma.toFixed(0)}`,
      `frame ${stats.frame.ms.toFixed(1)}ms`,
    ]
    // Only the debug/profiler engine builds fill triangle counts.
    if (stats.frame.triangles > 0) {
      lines.push(`tris  ${(stats.frame.triangles / 1000).toFixed(1)}k`)
    }
    this.el.textContent = lines.join('\n')
  }
}
