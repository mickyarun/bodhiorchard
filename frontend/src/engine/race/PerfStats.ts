// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
