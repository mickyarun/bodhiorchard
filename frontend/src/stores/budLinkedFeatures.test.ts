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
 * Contract test for the BUD↔Feature linkage store.
 *
 * The store is the only place the frontend talks to the
 * /api/v1/buds/{id}/linked-features endpoints, so the test verifies:
 *   • URL paths match the backend router exactly (camelCase wire format).
 *   • POST/DELETE both refetch — the POST response is a delta only, so
 *     trusting it would let concurrent PM-agent writes drift the cache.
 *   • Errors surface through the shared `error` ref, mirroring `bud.ts`.
 *
 * Axios is mocked entirely; no real HTTP roundtrip is needed.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/services/api', () => {
  const get = vi.fn()
  const post = vi.fn()
  const del = vi.fn()
  return { default: { get, post, delete: del } }
})

// Re-import after the mock factory is registered.
import api from '@/services/api'
import { useBudLinkedFeaturesStore } from './budLinkedFeatures'
import type { LinkedFeature } from '@/types'

const BUD_ID = 'bud-1'
const FEATURE_A: LinkedFeature = {
  id: 'feat-a',
  title: 'Bank Account Linking',
  linkType: 'touches',
  source: 'pm_agent',
  repoId: 'repo-1',
  repoName: 'acme-frontend',
  codeLocations: null,
}
const FEATURE_B: LinkedFeature = {
  ...FEATURE_A,
  id: 'feat-b',
  title: 'Notifications',
  source: 'manual',
  repoName: 'acme-backend',
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
})

describe('useBudLinkedFeaturesStore', () => {
  it('fetch() GETs the correct URL and caches rows under byBudId', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ data: [FEATURE_A, FEATURE_B] })

    const store = useBudLinkedFeaturesStore()
    const rows = await store.fetch(BUD_ID)

    expect(api.get).toHaveBeenCalledWith(`/v1/buds/${BUD_ID}/linked-features`)
    expect(rows).toEqual([FEATURE_A, FEATURE_B])
    expect(store.byBudId[BUD_ID]).toEqual([FEATURE_A, FEATURE_B])
    expect(store.error).toBe('')
  })

  it('fetch() surfaces the fallback message on a server error and returns null', async () => {
    // Shape an axios-like error so extractApiError takes the response path.
    vi.mocked(api.get).mockRejectedValueOnce({ response: { status: 500, data: {} } })

    const store = useBudLinkedFeaturesStore()
    const rows = await store.fetch(BUD_ID)

    expect(rows).toBeNull()
    expect(store.error).toBe('Failed to load linked features')
    expect(store.byBudId[BUD_ID]).toBeUndefined()
  })

  it('link() POSTs camelCase {featureIds} and refetches to refresh the cache', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: { insertedCount: 1, insertedFeatureIds: ['feat-b'] },
    })
    vi.mocked(api.get).mockResolvedValueOnce({ data: [FEATURE_A, FEATURE_B] })

    const store = useBudLinkedFeaturesStore()
    const resp = await store.link(BUD_ID, ['feat-b'])

    expect(api.post).toHaveBeenCalledWith(
      `/v1/buds/${BUD_ID}/linked-features`,
      { featureIds: ['feat-b'] },
    )
    expect(api.get).toHaveBeenCalledWith(`/v1/buds/${BUD_ID}/linked-features`)
    expect(resp).toEqual({ insertedCount: 1, insertedFeatureIds: ['feat-b'] })
    expect(store.byBudId[BUD_ID]).toEqual([FEATURE_A, FEATURE_B])
  })

  it('link() returns null and sets error when POST fails; does not refetch', async () => {
    vi.mocked(api.post).mockRejectedValueOnce({
      response: { status: 500, data: {} },
    })

    const store = useBudLinkedFeaturesStore()
    const resp = await store.link(BUD_ID, ['feat-b'])

    expect(resp).toBeNull()
    expect(store.error).toBe('Failed to link features')
    // Refetch must NOT run when the POST itself errored — that's what makes
    // the cache trustworthy after a failed mutation.
    expect(api.get).not.toHaveBeenCalled()
  })

  it('unlink() DELETEs the correct URL and refetches', async () => {
    vi.mocked(api.delete).mockResolvedValueOnce({})
    vi.mocked(api.get).mockResolvedValueOnce({ data: [FEATURE_A] })

    const store = useBudLinkedFeaturesStore()
    const ok = await store.unlink(BUD_ID, 'feat-b')

    expect(api.delete).toHaveBeenCalledWith(
      `/v1/buds/${BUD_ID}/linked-features/feat-b`,
    )
    expect(api.get).toHaveBeenCalledWith(`/v1/buds/${BUD_ID}/linked-features`)
    expect(ok).toBe(true)
    expect(store.byBudId[BUD_ID]).toEqual([FEATURE_A])
  })

  it('unlink() returns false and sets error when the DELETE fails', async () => {
    vi.mocked(api.delete).mockRejectedValueOnce({
      response: { status: 403, data: { detail: 'Insufficient permissions' } },
    })

    const store = useBudLinkedFeaturesStore()
    const ok = await store.unlink(BUD_ID, 'feat-b')

    expect(ok).toBe(false)
    // extractApiError surfaces the server's detail verbatim for 403s.
    expect(store.error).toBe('Insufficient permissions')
    // Refetch must NOT run when the DELETE itself errored.
    expect(api.get).not.toHaveBeenCalled()
  })
})
