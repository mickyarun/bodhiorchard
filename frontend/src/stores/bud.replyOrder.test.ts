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
 * A stage move that auto-assigns someone fires activity events before the
 * PATCH commits, and the page refreshes on them. Whatever order the GET and
 * PATCH replies land in, the page must end on the server's latest stage.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn(), patch: vi.fn() } }))

import api from '@/services/api'
import { useBUDStore } from '@/stores/bud'
import type { BUDDocument } from '@/types'

type Reply = (body: Partial<BUDDocument>) => Promise<void>

const get = vi.mocked(api.get)
const patch = vi.mocked(api.patch)
const gets: Reply[] = []
const patches: Reply[] = []

// Each call parks until the test answers it; answering also lets the
// store's continuation run before the test moves on.
function parked(queue: Reply[]) {
  return () => new Promise(ok => {
    queue.push(async body => {
      ok({ data: body, headers: {} })
      await flush()
    })
  })
}

async function flush(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await Promise.resolve()
}

function openBud(status: string) {
  const store = useBUDStore()
  store.currentBUD = { id: 'A', status, assignee_id: null } as unknown as BUDDocument
  return store
}

beforeEach(() => {
  setActivePinia(createPinia())
  gets.length = 0
  patches.length = 0
  get.mockReset().mockImplementation(parked(gets) as never)
  patch.mockReset().mockImplementation(parked(patches) as never)
})

describe('BUD replies landing out of order', () => {
  it('holds a refresh asked for mid-move until the move lands', async () => {
    const store = openBud('bud')
    const move = store.updateBUD('A', { status: 'design' })
    // skill_completed from auto-assignment arrives before the PATCH commits.
    const refresh = store.refreshBUDIfCurrent('A')
    await flush()
    expect(get).not.toHaveBeenCalled()

    await patches[0]({ id: 'A', status: 'design', assignee_id: null })
    await move
    expect(store.currentBUD?.status).toBe('design')

    await gets[0]({ id: 'A', status: 'design', assignee_id: 'sofia' })
    await refresh
    expect(store.currentBUD).toMatchObject({ status: 'design', assignee_id: 'sofia' })
  })

  it('drops a refresh sent before a move when it lands after it', async () => {
    const store = openBud('design')
    const refresh = store.refreshBUDIfCurrent('A')
    await flush()
    const move = store.updateBUD('A', { status: 'tech_arch' })

    await patches[0]({ id: 'A', status: 'tech_arch' })
    await move
    await gets[0]({ id: 'A', status: 'design' })
    await refresh
    expect(store.currentBUD?.status).toBe('tech_arch')
  })

  it('keeps the newer of two refreshes', async () => {
    const store = openBud('bud')
    const older = store.refreshBUDIfCurrent('A')
    await flush()
    const newer = store.refreshBUDIfCurrent('A')
    await flush()

    await gets[1]({ id: 'A', status: 'design', assignee_id: 'sofia' })
    await newer
    await gets[0]({ id: 'A', status: 'bud' })
    await older
    expect(store.currentBUD).toMatchObject({ status: 'design', assignee_id: 'sofia' })
  })

  it('still refreshes once a failed move settles', async () => {
    const store = openBud('bud')
    patch.mockRejectedValueOnce(new Error('Network Error'))
    const move = store.updateBUD('A', { status: 'design' })
    const refresh = store.refreshBUDIfCurrent('A')
    await move
    await flush()

    await gets[0]({ id: 'A', status: 'bud', assignee_id: null })
    await refresh
    expect(store.currentBUD?.status).toBe('bud')
  })
})
