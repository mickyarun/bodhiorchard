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
 * PerfStats — thin wrapper around pc.MiniStats, enabled only when the race
 * route is opened with ?stats=1 (or ?stats=true). Keeps the HUD overlay
 * out of the way during normal play; available for baseline measurement
 * and regression testing per the README perf budget.
 *
 * Usage:
 *   const stats = new PerfStats(app)
 *   if (shouldEnableStats()) stats.enable()
 *   // …
 *   stats.destroy()
 */
import * as pc from 'playcanvas'

export function shouldEnableStats(): boolean {
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  const v = params.get('stats')
  return v === '1' || v === 'true'
}

export class PerfStats {
  private miniStats: pc.MiniStats | null = null

  constructor(private app: pc.AppBase) {}

  enable(): void {
    if (this.miniStats) return
    this.miniStats = new pc.MiniStats(this.app)
  }

  destroy(): void {
    // pc.MiniStats doesn't expose a destroy() in the public types; it is
    // owned by the Application and cleaned up when the app is destroyed.
    // Null out the reference so repeated destroy calls are no-ops.
    this.miniStats = null
  }
}
