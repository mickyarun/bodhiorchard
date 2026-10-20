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
 * The reports store's loading rules: the scope call decides access and
 * clears a previous viewer's state, and a slow report never overwrites a
 * newer one.
 */
import { AxiosError, AxiosHeaders } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn() } }))

import api from '@/services/api'
import { outOfScope, useLeaveReportsStore } from '@/stores/leaveReports'
import type { ReportScope, SummaryReport } from '@/types/leaveReports'

const get = vi.mocked(api.get)

const SCOPE: ReportScope = {
  all: false,
  people: [{ user_id: 'u1', name: 'Asha' }],
  departments: ['Sales'],
  offices: [{ id: 'o1', name: 'Chennai' }],
  policies: [{ id: 'p1', name: 'India' }],
  leave_types: [{ id: 't1', name: 'Casual' }],
  current_leave_years: [2026],
}

function failWith(status: number): AxiosError {
  const config = { headers: new AxiosHeaders() }
  return new AxiosError('failed', String(status), config, null, {
    status,
    statusText: '',
    headers: {},
    config,
    data: { detail: 'Server error' },
  })
}

function summary(start: string): SummaryReport {
  return { start, end: start, leave_types: [], rows: [] }
}

beforeEach(() => {
  setActivePinia(createPinia())
  get.mockReset()
})

describe('loadScope', () => {
  it('treats a 403 as no access, not an error', async () => {
    get.mockRejectedValueOnce(failWith(403))
    const store = useLeaveReportsStore()
    await store.loadScope()
    expect(store.noAccess).toBe(true)
    expect(store.scopeError).toBe('')
    expect(store.scope).toBeNull()
  })

  it('keeps a failed scope load visible after a report fetch', async () => {
    get.mockRejectedValueOnce(failWith(500)).mockResolvedValueOnce({ data: summary('2026-06-01') })
    const store = useLeaveReportsStore()
    await store.loadScope()
    await store.fetch()
    expect(store.noAccess).toBe(false)
    expect(store.scopeError).not.toBe('')
    expect(store.error).toBe('')
  })

  it("drops the previous viewer's reports and out-of-scope picks", async () => {
    const store = useLeaveReportsStore()
    store.summary = summary('2026-01-01')
    Object.assign(store.filters, { user_id: 'someone-else', office_id: 'o1', department: 'Ops' })
    get.mockResolvedValueOnce({ data: SCOPE })
    await store.loadScope()
    expect(store.summary).toBeNull()
    expect(store.filters.user_id).toBeNull()
    expect(store.filters.department).toBeNull()
    expect(store.filters.office_id).toBe('o1')
    expect(store.scope).toEqual(SCOPE)
  })
})

describe('outOfScope', () => {
  it('names only the filters set to something the scope lacks', () => {
    const store = useLeaveReportsStore()
    Object.assign(store.filters, { manager_id: 'u9', policy_id: 'p1', leave_type_id: 't2' })
    expect(outOfScope(store.filters, SCOPE).sort()).toEqual(['leave_type_id', 'manager_id'])
  })
})

describe('fetch', () => {
  it('ignores a response that arrives after a newer one', async () => {
    let releaseOld: (value: { data: SummaryReport }) => void = () => {}
    get
      .mockReturnValueOnce(new Promise(resolve => (releaseOld = resolve)))
      .mockResolvedValueOnce({ data: summary('2026-07-01') })
    const store = useLeaveReportsStore()
    const old = store.fetch()
    await store.fetch()
    releaseOld({ data: summary('2026-06-01') })
    await old
    expect(store.summary?.start).toBe('2026-07-01')
    expect(store.loading).toBe(false)
  })
})

describe('setPreset', () => {
  it('keeps the current range when switching to custom', () => {
    const store = useLeaveReportsStore()
    Object.assign(store.filters, { start: '2026-02-03', end: '2026-02-09' })
    store.setPreset('custom')
    expect(store.preset).toBe('custom')
    expect([store.filters.start, store.filters.end]).toEqual(['2026-02-03', '2026-02-09'])
  })
})
