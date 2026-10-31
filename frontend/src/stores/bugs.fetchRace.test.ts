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
 * Switching the Bugs page's environment while the first board is still
 * loading: whichever reply lands last, the board shows the newer filter.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn() } }))

import api from '@/services/api'
import { useBugsStore } from '@/stores/bugs'

const get = vi.mocked(api.get)
const replies = new Map<string, { ok: (v: unknown) => void; fail: (e: unknown) => void }>()

const card = (id: string) => ({ id, status: 'open' })
const board = (id: string) => ({ data: { columns: { open: [card(id)] }, total: 1 } })
const list = (id: string) => ({ data: { items: [card(id)], total: 1, page: 1, pageSize: 20 } })

beforeEach(() => {
  setActivePinia(createPinia())
  replies.clear()
  get.mockReset()
  get.mockImplementation((_url: string, config?: { params?: Record<string, string> }) =>
    new Promise((ok, fail) => {
      const params = config?.params ?? {}
      replies.set(params.bugType ?? params.budId ?? '', { ok, fail })
    }))
})

describe('fetchBoard when a newer load overtakes it', () => {
  it('keeps the newer board when the older reply lands last', async () => {
    const store = useBugsStore()
    const older = store.fetchBoard({ bugType: 'production' })
    const newer = store.fetchBoard({ bugType: 'all' })
    replies.get('all')!.ok(board('from-all'))
    await newer
    replies.get('production')!.ok(board('from-production'))
    await older
    expect(store.board.open.map((b) => b.id)).toEqual(['from-all'])
    expect(store.boardLoading).toBe(false)
  })

  it('stays loading until the newer load answers', async () => {
    const store = useBugsStore()
    const older = store.fetchBoard({ bugType: 'production' })
    const newer = store.fetchBoard({ bugType: 'all' })
    replies.get('production')!.ok(board('from-production'))
    await older
    expect(store.boardLoading).toBe(true)
    replies.get('all')!.ok(board('from-all'))
    await newer
    expect(store.board.open.map((b) => b.id)).toEqual(['from-all'])
    expect(store.boardLoading).toBe(false)
  })

  it("ignores the older load's failure", async () => {
    const store = useBugsStore()
    const older = store.fetchBoard({ bugType: 'production' })
    const newer = store.fetchBoard({ bugType: 'all' })
    replies.get('all')!.ok(board('from-all'))
    await newer
    replies.get('production')!.fail(new Error('Network Error'))
    await older
    expect(store.loadError).toBeNull()
  })
})

describe('fetchBugs when a newer load overtakes it', () => {
  it('keeps the newer list when the older reply lands last', async () => {
    const store = useBugsStore()
    const older = store.fetchBugs({ budId: 'bud-a' })
    const newer = store.fetchBugs({ budId: 'bud-b' })
    replies.get('bud-b')!.ok(list('from-b'))
    await newer
    replies.get('bud-a')!.ok(list('from-a'))
    await older
    expect(store.bugs.map((b) => b.id)).toEqual(['from-b'])
    expect(store.loading).toBe(false)
  })
})
