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
 * The caller's own leave: errors come back as sentences, a sent or
 * cancelled request refreshes balances and the list, an older list fetch
 * never overwrites a newer one, and the approvals badge hides on failure.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LeaveRequestCreate } from '@/types/leave'

vi.mock('@/services/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '@/services/api'
import { useLeaveStore } from '@/stores/leave'

const get = vi.mocked(api.get)
const post = vi.mocked(api.post)
const BODY = { kind: 'wfh', start_date: '2026-11-02', end_date: '2026-11-02' } as LeaveRequestCreate

function conflict(detail: string): Error {
  return Object.assign(new Error('409'), { response: { status: 409, data: { detail } } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  get.mockReset()
  post.mockReset()
  get.mockImplementation(async (url: string) => ({ data: url.endsWith('/summary') ? { types: [] } : [] }))
})

describe('fetchSummary', () => {
  it('shows a reload hint when balances fail to load', async () => {
    get.mockRejectedValue(Object.assign(new Error('500'), { response: { status: 500, data: {} } }))
    const store = useLeaveStore()
    await store.fetchSummary()
    expect(store.summaryError).toBe("Couldn't load your leave balances. Reload to try again.")
    expect(store.summaryLoading).toBe(false)
  })
})

describe('fetchRequests', () => {
  it('keeps the newest scope when an older fetch answers last', async () => {
    const answers: Record<string, (v: unknown) => void> = {}
    get.mockImplementation((_url: string, config?: { params?: { scope?: string } }) =>
      new Promise(resolve => { answers[config!.params!.scope!] = resolve }))
    const store = useLeaveStore()
    const older = store.fetchRequests('upcoming')
    const newer = store.fetchRequests('past')
    answers.past({ data: [{ id: 'past-1' }] })
    await newer
    answers.upcoming({ data: [{ id: 'upcoming-1' }] })
    await older
    expect(store.scope).toBe('past')
    expect(store.requests).toEqual([{ id: 'past-1' }])
    expect(store.requestsLoading).toBe(false)
  })

  it("ignores an older fetch's failure", async () => {
    let failOld: (e: unknown) => void = () => undefined
    get.mockImplementationOnce(() => new Promise((_, reject) => { failOld = reject }))
    get.mockResolvedValueOnce({ data: [] })
    const store = useLeaveStore()
    const older = store.fetchRequests('upcoming')
    await store.fetchRequests('past')
    failOld(new Error('Network Error'))
    await older
    expect(store.requestsError).toBe('')
  })
})

describe('createRequest', () => {
  it('sends the request and refreshes balances and the list', async () => {
    post.mockResolvedValue({ data: {} })
    const store = useLeaveStore()
    expect(await store.createRequest(BODY)).toBeNull()
    expect(post).toHaveBeenCalledWith('/v1/leave/requests', BODY)
    expect(get).toHaveBeenCalledWith('/v1/leave/me/summary')
    expect(get).toHaveBeenCalledWith('/v1/leave/me/requests', { params: { scope: 'upcoming' } })
  })

  it("returns the server's reason and refreshes nothing", async () => {
    post.mockRejectedValue(conflict('Overlaps an existing request'))
    const store = useLeaveStore()
    expect(await store.createRequest(BODY)).toBe('Overlaps an existing request')
    expect(get).not.toHaveBeenCalled()
  })
})

describe('cancelRequest', () => {
  it('cancels and refreshes, or explains why not', async () => {
    post.mockResolvedValueOnce({ data: {} })
    const store = useLeaveStore()
    expect(await store.cancelRequest('r1')).toBeNull()
    expect(post).toHaveBeenCalledWith('/v1/leave/requests/r1/cancel')
    expect(get).toHaveBeenCalledTimes(2)

    post.mockRejectedValueOnce(new Error('Network Error'))
    expect(await store.cancelRequest('r1')).toBe('Network error. Please check your connection.')
  })
})

describe('preview', () => {
  it('returns the data, or a retry message without data', async () => {
    post.mockResolvedValueOnce({ data: { days: '1' } })
    const store = useLeaveStore()
    expect(await store.preview(BODY)).toEqual({ data: { days: '1' }, error: '' })
    post.mockRejectedValueOnce(Object.assign(new Error('500'), { response: { status: 500, data: {} } }))
    expect(await store.preview(BODY)).toEqual({ data: null, error: "Couldn't check this request. Try again." })
  })
})

describe('fetchApprovalCount', () => {
  it('hides the badge when the count fails to load', async () => {
    get.mockResolvedValueOnce({ data: { pending: 4, is_approver: true, has_reports: true } })
    const store = useLeaveStore()
    await store.fetchApprovalCount()
    expect(store.approvalCount.pending).toBe(4)
    get.mockRejectedValueOnce(new Error('Network Error'))
    await store.fetchApprovalCount()
    expect(store.approvalCount).toEqual({ pending: 0, is_approver: false, has_reports: false })
  })
})
