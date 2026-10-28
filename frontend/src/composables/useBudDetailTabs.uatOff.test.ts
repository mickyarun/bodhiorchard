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
 * A BUD can sit in UAT after the org turns UAT off. The page has no UAT
 * tab or panel then, so asking for that tab (the stage tab on load, or a
 * ``?tab=uat`` link) must land on Prod instead of a blank panel, the same
 * as switching UAT off while the tab is open.
 */
import { describe, expect, it, vi } from 'vitest'
import { computed, nextTick, reactive, ref } from 'vue'

const settings = vi.hoisted(() => ({ connections: {} as { budStages?: { uatEnabled: boolean } } }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => settings }))

import { useBudDetailTabs } from '@/composables/useBudDetailTabs'
import type { BUDDocument } from '@/types'

function uatBudWithUatOff() {
  settings.connections = reactive({ budStages: { uatEnabled: false } })
  const bud = ref({ id: 'bud-1', status: 'uat', designs: [] } as unknown as BUDDocument)
  return useBudDetailTabs(computed(() => bud.value))
}

describe('a BUD in UAT while the org has UAT off', () => {
  it('opens Prod when the UAT tab is asked for', async () => {
    const t = uatBudWithUatOff()
    expect(t.tabs.value.map(x => x.value)).not.toContain('uat')
    t.activeTab.value = 'uat'
    await nextTick()
    expect(t.activeTab.value).toBe('prod')
  })

  it('leaves other tabs alone', async () => {
    const t = uatBudWithUatOff()
    t.activeTab.value = 'testing'
    await nextTick()
    expect(t.activeTab.value).toBe('testing')
  })
})
