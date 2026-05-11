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

import { onScopeDispose, watch, type Ref } from 'vue'

/**
 * Poll a callback on an interval, but only while the tab is visible AND
 * the caller-provided ``active`` flag is true.
 *
 * Used by the GitHub App connection card to re-fetch
 * ``GET /v1/settings/connections`` while the install webhook is still
 * pending. Pausing on ``visibilitychange`` keeps the request volume down
 * when the user has tabbed away to GitHub to install the app, then
 * resumes the moment they tab back so the card flips to READY without a
 * full page reload.
 *
 * Cleans up timer and listener on component unmount.
 */
export function useFocusAwarePoll(
  callback: () => Promise<void>,
  intervalMs: number,
  options: { active: Ref<boolean> },
): void {
  let timerId: ReturnType<typeof setInterval> | null = null

  function isVisible(): boolean {
    // ``document`` is undefined in SSR / pure-node test contexts; treat
    // "no document" as "not visible" so the poll never starts.
    return typeof document !== 'undefined' && document.visibilityState === 'visible'
  }

  function stop(): void {
    if (timerId !== null) {
      clearInterval(timerId)
      timerId = null
    }
  }

  function start(): void {
    if (timerId !== null) {
      return
    }
    timerId = setInterval(() => {
      void callback()
    }, intervalMs)
  }

  function reconcile(): void {
    if (options.active.value && isVisible()) {
      start()
    } else {
      stop()
    }
  }

  function onVisibilityChange(): void {
    reconcile()
  }

  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }

  watch(options.active, reconcile, { immediate: true })

  // ``onScopeDispose`` covers both component unmount and explicit
  // ``effectScope().stop()`` — the latter is what unit tests use.
  onScopeDispose(() => {
    stop()
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  })
}
