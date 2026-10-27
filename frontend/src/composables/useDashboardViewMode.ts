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

import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export type DashboardViewMode = 'overview' | 'graph' | 'garden'

const MODES: readonly DashboardViewMode[] = ['overview', 'graph', 'garden']

/**
 * The dashboard view, kept in ``?view=`` so a link or reload returns to it.
 * Overview is the default and leaves the query clean. Switching replaces
 * the history entry rather than pushing one.
 */
export function useDashboardViewMode() {
  const route = useRoute()
  const router = useRouter()

  return computed<DashboardViewMode>({
    get() {
      const raw = route.query.view
      return MODES.find(m => m === raw) ?? 'overview'
    },
    set(mode) {
      void router.replace({
        query: { ...route.query, view: mode === 'overview' ? undefined : mode },
      })
    },
  })
}
