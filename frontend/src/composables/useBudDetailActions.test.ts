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

/** Edits from the BUD detail header: what each sends, and what it skips. */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import type { BUDDocument } from '@/types'

const h = vi.hoisted(() => ({
  push: vi.fn(),
  store: {
    updateBUD: vi.fn(),
    deleteBUD: vi.fn(),
    refreshBUDIfCurrent: vi.fn(),
  },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: h.push }) }))
vi.mock('@/stores/bud', () => ({ useBUDStore: () => h.store }))

import { useBudDetailActions } from '@/composables/useBudDetailActions'

const bud = ref<BUDDocument | null>(null)
const loadTimeline = vi.fn(async () => undefined)

function actions() {
  return useBudDetailActions(computed(() => bud.value), loadTimeline)
}

beforeEach(() => {
  vi.clearAllMocks()
  bud.value = { id: 'bud-1', priority: 'P2' } as unknown as BUDDocument
  h.store.updateBUD.mockResolvedValue({})
  h.store.refreshBUDIfCurrent.mockResolvedValue(undefined)
})

describe('useBudDetailActions', () => {
  it('saves a title and reloads the timeline', async () => {
    await actions().saveTitle('Passkey sign-in')
    expect(h.store.updateBUD).toHaveBeenCalledWith('bud-1', { title: 'Passkey sign-in' })
    expect(loadTimeline).toHaveBeenCalledOnce()
  })

  it('can unassign', async () => {
    await actions().changeAssignee(null)
    expect(h.store.updateBUD).toHaveBeenCalledWith('bud-1', { assignee_id: null })
  })

  it('skips a priority that did not change', async () => {
    await actions().changePriority('P2')
    expect(h.store.updateBUD).not.toHaveBeenCalled()
    await actions().changePriority('P0')
    expect(h.store.updateBUD).toHaveBeenCalledWith('bud-1', { priority: 'P0' })
  })

  it('goes back to the board only when the delete went through', async () => {
    h.store.deleteBUD.mockResolvedValueOnce(false)
    await actions().deleteBud()
    expect(h.push).not.toHaveBeenCalled()
    h.store.deleteBUD.mockResolvedValueOnce(true)
    await actions().deleteBud()
    expect(h.push).toHaveBeenCalledWith('/buds')
  })

  it('does nothing before the BUD has loaded', async () => {
    bud.value = null
    const a = actions()
    await a.saveTitle('x')
    await a.changeAssignee('u1')
    await a.changePriority('P0')
    await a.deleteBud()
    await a.refreshBudAndTimeline()
    expect(h.store.updateBUD).not.toHaveBeenCalled()
    expect(h.store.deleteBUD).not.toHaveBeenCalled()
    expect(loadTimeline).not.toHaveBeenCalled()
  })

  it('refreshes the BUD and its timeline together', async () => {
    await actions().refreshBudAndTimeline()
    expect(h.store.refreshBUDIfCurrent).toHaveBeenCalledWith('bud-1')
    expect(loadTimeline).toHaveBeenCalledOnce()
  })

  it('logs rather than throws when the refresh after a settings save fails', async () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    h.store.refreshBUDIfCurrent.mockRejectedValueOnce(new Error('offline'))
    await expect(actions().refreshAfterSettingsSave()).resolves.toBeUndefined()
    expect(log).toHaveBeenCalledOnce()
    log.mockRestore()
  })
})
