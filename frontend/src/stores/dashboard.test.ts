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

/** The code map's data on the dashboard: loading, refresh, and the error shown. */
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn() } }))

import api from '@/services/api'
import { useDashboardStore } from '@/stores/dashboard'

const get = vi.mocked(api.get)
const NOW = new Date('2026-10-28T09:30:00Z')

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  setActivePinia(createPinia())
  get.mockReset()
})

afterEach(() => vi.useRealTimers())

describe('fetchTreeData', () => {
  it('keeps the data and when it was loaded', async () => {
    get.mockResolvedValue({ data: { repos: [] } })
    const store = useDashboardStore()
    await store.fetchTreeData()
    expect(get).toHaveBeenCalledWith('/v1/dashboard/tree-data', { params: {}, timeout: 120000 })
    expect(store.treeData).toEqual({ repos: [] })
    expect(store.loadedAt).toEqual(NOW)
    expect(store.loading).toBe(false)
    expect(store.error).toBeNull()
  })

  it('asks the server to rebuild on refresh', async () => {
    get.mockResolvedValue({ data: {} })
    await useDashboardStore().fetchTreeData(true)
    expect(get.mock.calls[0][1]).toMatchObject({ params: { refresh: 'true' } })
  })

  it('shows a reload hint on failure and keeps the last good data', async () => {
    get.mockResolvedValueOnce({ data: { repos: ['a'] } })
    get.mockRejectedValueOnce(new Error('timeout'))
    const store = useDashboardStore()
    await store.fetchTreeData()
    await store.fetchTreeData()
    expect(store.error).toBe("Couldn't load the code map. Reload to try again.")
    expect(store.treeData).toEqual({ repos: ['a'] })
    expect(store.loading).toBe(false)
  })

  it('clears the previous error on the next try', async () => {
    get.mockRejectedValueOnce(new Error('timeout'))
    get.mockResolvedValueOnce({ data: {} })
    const store = useDashboardStore()
    await store.fetchTreeData()
    await store.fetchTreeData()
    expect(store.error).toBeNull()
  })
})
