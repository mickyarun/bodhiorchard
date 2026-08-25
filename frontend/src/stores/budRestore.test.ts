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
 * Contract test for restoring a discarded BUD.
 *
 * Restore is a POST to a dedicated endpoint rather than a status PATCH —
 * the backend refuses status writes on terminal BUDs — so this pins:
 *   • the URL matches the backend router (/v1/buds/{id}/restore),
 *   • the response replaces the board row AND currentBUD, which is what
 *     moves the card out of the Discarded column without a refetch,
 *   • the backend's rejection detail reaches `error` verbatim, so the
 *     UI can explain *why* (e.g. a closed BUD is not restorable).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/services/api', () => {
  const get = vi.fn()
  const post = vi.fn()
  const patch = vi.fn()
  const del = vi.fn()
  return { default: { get, post, patch, delete: del } }
})

// Re-import after the mock factory is registered.
import api from '@/services/api'
import { useBUDStore } from './bud'
import type { BUDDocument, BUDListItem } from '@/types'

const BUD_ID = 'bud-1'
const DISCARDED_ROW: BUDListItem = {
  id: BUD_ID,
  bud_number: 12,
  title: 'Retry logic',
  status: 'discarded',
  priority: 'P2',
  complexity: null,
  prod_p70_date: null,
  current_phase_deadline: null,
  assignee_id: null,
  assignee_name: null,
  open_bug_count: 3,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-02T00:00:00Z',
}
// The server's restore payload is a BUDRead, which carries no
// ``open_bug_count`` — that transient is injected by the list endpoint
// only. Omitting it here is what makes the store's carry-over line
// testable: a plain `buds[idx] = data` would blank the bug badge.
const { open_bug_count: _omitted, ...RESTORE_RESPONSE } = {
  ...DISCARDED_ROW,
  status: 'testing' as const,
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
})

describe('useBUDStore.restoreBUD', () => {
  it('POSTs the restore endpoint and swaps the row in buds + currentBUD', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({ data: RESTORE_RESPONSE })

    const store = useBUDStore()
    store.buds = [DISCARDED_ROW]
    store.currentBUD = DISCARDED_ROW as BUDDocument

    const result = await store.restoreBUD(BUD_ID)

    expect(api.post).toHaveBeenCalledWith(`/v1/buds/${BUD_ID}/restore`)
    expect(result).toEqual(RESTORE_RESPONSE)
    // The card must move columns off this response alone — a stale row
    // here would leave it sitting in Discarded until a full refetch.
    expect(store.buds[0].status).toBe('testing')
    expect(store.currentBUD?.status).toBe('testing')
    // Carried over from the row being replaced, not from the response.
    expect(store.buds[0].open_bug_count).toBe(3)
    expect(store.error).toBe('')
  })

  it('surfaces the backend detail and leaves the row untouched on rejection', async () => {
    vi.mocked(api.post).mockRejectedValueOnce({
      response: { status: 409, data: { detail: "Only discarded BUDs can be restored; this one is 'closed'." } },
    })

    const store = useBUDStore()
    store.buds = [DISCARDED_ROW]

    const result = await store.restoreBUD(BUD_ID)

    expect(result).toBeNull()
    expect(store.error).toBe("Only discarded BUDs can be restored; this one is 'closed'.")
    expect(store.buds[0].status).toBe('discarded')
  })
})
