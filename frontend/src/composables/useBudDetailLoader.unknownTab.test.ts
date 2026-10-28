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
 * A ``?tab=`` the page doesn't know is treated like no ``?tab=``: the BUD
 * opens on its stage tab, not on whatever tab the previous BUD had open
 * (which the new BUD may not have, e.g. Closed).
 */
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { computed, effectScope, ref } from 'vue'
import type { BUDDocument } from '@/types'

const h = vi.hoisted(() => ({
  route: { params: { id: 'B' }, query: { tab: 'nonsense' } as Record<string, string> },
  settings: { connectionsLoaded: true, repos: [{}], fetchConnections: vi.fn(), fetchRepos: vi.fn() },
}))
const current = ref<BUDDocument | null>(null)
vi.mock('vue-router', () => ({ useRoute: () => h.route }))
vi.mock('@/stores/bud', () => ({
  useBUDStore: () => ({
    fetchBUD: async (id: string) => { current.value = { id, status: 'code_review' } as unknown as BUDDocument },
    refreshBUDIfCurrent: vi.fn(),
  }),
}))
vi.mock('@/stores/members', () => ({ useMembersStore: () => ({ fetchMembers: vi.fn() }) }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => h.settings }))
vi.mock('@/composables/useBudActivityChannel', () => ({
  useBudActivityChannel: () => ({ connect: vi.fn(), disconnect: vi.fn() }),
}))

import { useBudDetailLoader } from '@/composables/useBudDetailLoader'

describe('an unknown ?tab= link', () => {
  it('opens the BUD on its stage tab', async () => {
    // The previous BUD was closed and on its Closed tab.
    const activeTab = ref('closed')
    const scope = effectScope()
    scope.run(() => useBudDetailLoader({
      bud: computed(() => current.value),
      activeTab,
      startNewSession: vi.fn(),
      loadChatHistory: async () => undefined,
      loadTimeline: async () => undefined,
      reloadEstimates: vi.fn(),
      onLearningRecorded: vi.fn(),
    }))
    await flushPromises()
    expect(current.value?.id).toBe('B')
    expect(activeTab.value).toBe('code-review')
    scope.stop()
  })
})
