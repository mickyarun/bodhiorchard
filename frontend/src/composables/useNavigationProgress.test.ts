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
 * ``useNavigationProgress`` is a module-level singleton: the router guards
 * flip the flag and the layout reads it, so the contract that makes the
 * whole feature work is that *every* caller observes the *same* ``navigating``
 * ref. These tests pin that identity invariant plus the start/stop toggles.
 *
 * State lives at module scope and therefore leaks across tests, so each test
 * resets to a known baseline via the public ``stop()`` rather than relying on
 * order. The initial-default case re-imports the module in isolation so the
 * assertion reflects a fresh load, not whatever a prior test left behind.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useNavigationProgress } from './useNavigationProgress'

describe('useNavigationProgress', () => {
  beforeEach(() => {
    // Known baseline — the singleton persists between tests.
    useNavigationProgress().stop()
  })

  it('defaults to not navigating on a fresh module load', async () => {
    vi.resetModules()
    const fresh = await import('./useNavigationProgress')
    expect(fresh.useNavigationProgress().navigating.value).toBe(false)
  })

  it('start() sets navigating true and stop() clears it', () => {
    const { navigating, start, stop } = useNavigationProgress()
    expect(navigating.value).toBe(false)
    start()
    expect(navigating.value).toBe(true)
    stop()
    expect(navigating.value).toBe(false)
  })

  it('shares one navigating ref across every caller', () => {
    // The router guard and the layout call the composable separately; the
    // feature is silently broken if they get independent refs.
    const guard = useNavigationProgress()
    const layout = useNavigationProgress()
    expect(layout.navigating).toBe(guard.navigating)

    guard.start()
    expect(layout.navigating.value).toBe(true)
    layout.stop()
    expect(guard.navigating.value).toBe(false)
  })

  it('start() is idempotent — overlapping navigations stay lit', () => {
    // Two navigations in flight (the "user keeps clicking" case) call start()
    // twice; a single stop() must still clear, mirroring the router's
    // one-stop-per-settle accounting.
    const { navigating, start, stop } = useNavigationProgress()
    start()
    start()
    expect(navigating.value).toBe(true)
    stop()
    expect(navigating.value).toBe(false)
  })
})
