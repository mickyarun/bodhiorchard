/*
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { ref } from 'vue'

/**
 * Single source of truth for "a route navigation is in flight".
 *
 * Flipped by the router guards (``beforeEach`` → start, ``afterEach`` /
 * ``onError`` → stop) and consumed by the layout-level progress bar.
 * Living one level above the destination component is the whole point: a
 * lazily-imported view (e.g. ``BUDDetail.vue``) cannot render its own
 * spinner until its JS chunk has already downloaded and mounted, so the
 * worst part of the wait — chunk fetch + route resolution — has no
 * in-component feedback. This bar reacts the instant the link is clicked,
 * closing that dead zone.
 *
 * A plain boolean is correct because vue-router serialises navigations and
 * cancels any superseded one: ``afterEach`` fires only for the navigation
 * that actually settles (including redirects and failures), so it always
 * clears the flag exactly once after the final landing.
 */
const navigating = ref(false)

export function useNavigationProgress() {
  return {
    navigating,
    start(): void {
      navigating.value = true
    },
    stop(): void {
      navigating.value = false
    },
  }
}
