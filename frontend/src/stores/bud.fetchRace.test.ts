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
 * Moving from BUD A to BUD B while A is still loading: whichever reply
 * lands last, the page shows B, so header edits never reach A.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn() } }))

import api from '@/services/api'
import { useBUDStore } from '@/stores/bud'

const get = vi.mocked(api.get)
const replies = new Map<string, { ok: (v: unknown) => void; fail: (e: unknown) => void }>()

beforeEach(() => {
  setActivePinia(createPinia())
  replies.clear()
  get.mockReset()
  get.mockImplementation((url: string) => new Promise((ok, fail) => {
    replies.set(url.split('/').pop()!, { ok, fail })
  }))
})

describe('fetchBUD when a newer load overtakes it', () => {
  it('keeps the newer BUD when the older reply lands last', async () => {
    const store = useBUDStore()
    const a = store.fetchBUD('A')
    const b = store.fetchBUD('B')
    replies.get('B')!.ok({ data: { id: 'B' } })
    await b
    replies.get('A')!.ok({ data: { id: 'A' } })
    await a
    expect(store.currentBUD?.id).toBe('B')
    expect(store.loading).toBe(false)
  })

  it('stays loading until the newer load answers', async () => {
    const store = useBUDStore()
    const a = store.fetchBUD('A')
    const b = store.fetchBUD('B')
    replies.get('A')!.ok({ data: { id: 'A' } })
    await a
    expect(store.loading).toBe(true)
    replies.get('B')!.ok({ data: { id: 'B' } })
    await b
    expect(store.currentBUD?.id).toBe('B')
    expect(store.loading).toBe(false)
  })

  it("ignores the older load's failure", async () => {
    const store = useBUDStore()
    const a = store.fetchBUD('A')
    const b = store.fetchBUD('B')
    replies.get('B')!.ok({ data: { id: 'B' } })
    await b
    replies.get('A')!.fail(new Error('Network Error'))
    await a
    expect(store.error).toBe('')
    expect(store.currentBUD?.id).toBe('B')
  })
})
