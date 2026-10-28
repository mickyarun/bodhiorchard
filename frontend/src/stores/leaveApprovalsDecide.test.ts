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
 * Deciding leave in the approvals queue: a decided card leaves and the
 * badge refreshes; a request someone else decided first (409) explains
 * itself and reloads the queue; approved leave can be withdrawn or moved.
 */
import { createPinia, setActivePinia } from 'pinia'
import { AxiosError, AxiosHeaders } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApprovalItem } from '@/types/leave'

const h = vi.hoisted(() => ({ fetchApprovalCount: vi.fn() }))
vi.mock('@/services/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 'hr' } }) }))
vi.mock('@/stores/leave', () => ({ useLeaveStore: () => ({ fetchApprovalCount: h.fetchApprovalCount }) }))

import api from '@/services/api'
import { approvalParams, useLeaveApprovalsStore } from '@/stores/leaveApprovals'

const get = vi.mocked(api.get)
const post = vi.mocked(api.post)

function item(id: string, name: string, type: string | null = 'casual'): ApprovalItem {
  return {
    request: {
      id,
      user: { user_id: `u-${name}`, name },
      leave_type: type ? { id: type, name: type } : null,
    },
  } as unknown as ApprovalItem
}

function axios409(detail: string): AxiosError {
  const config = { headers: new AxiosHeaders() }
  return new AxiosError('409', 'ERR_BAD_REQUEST', config, null, {
    status: 409, statusText: 'Conflict', headers: {}, config, data: { detail },
  })
}

async function storeWith(items: ApprovalItem[]) {
  get.mockResolvedValue({ data: { items, truncated: false } })
  const store = useLeaveApprovalsStore()
  await store.fetch()
  return store
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('approvalParams', () => {
  it('sends only the filters that are set', () => {
    expect(approvalParams('decided', { start: '2026-11-01', end: '', kind: null, leave_type_id: 'sick', user_id: null }))
      .toEqual({ status: 'decided', start: '2026-11-01', leave_type_id: 'sick' })
  })
})

describe('approve and reject', () => {
  it('removes the decided card and refreshes the badge', async () => {
    const store = await storeWith([item('r1', 'Ravi'), item('r2', 'Asha')])
    post.mockResolvedValue({ data: {} })
    expect(await store.approve('r1', '  ')).toBeNull()
    expect(post).toHaveBeenCalledWith('/v1/leave/requests/r1/approve', { note: null })
    expect(store.items.map(i => i.request.id)).toEqual(['r2'])
    expect(h.fetchApprovalCount).toHaveBeenCalledOnce()
  })

  it('sends a trimmed note with a rejection', async () => {
    const store = await storeWith([item('r1', 'Ravi')])
    post.mockResolvedValue({ data: {} })
    await store.reject('r1', '  Release week  ')
    expect(post).toHaveBeenCalledWith('/v1/leave/requests/r1/reject', { note: 'Release week' })
  })

  it('explains a request decided elsewhere and reloads the queue', async () => {
    const store = await storeWith([item('r1', 'Ravi')])
    get.mockClear()
    post.mockRejectedValue(axios409('Already approved by Asha'))
    expect(await store.approve('r1', '')).toBe('Already approved by Asha')
    expect(store.notice).toBe('Already approved by Asha')
    expect(get).toHaveBeenCalledWith('/v1/leave/approvals', expect.anything())
    expect(h.fetchApprovalCount).toHaveBeenCalled()
  })

  it('keeps the card and sets no notice for other failures', async () => {
    const store = await storeWith([item('r1', 'Ravi')])
    post.mockRejectedValue(new Error('Network Error'))
    expect(await store.reject('r1', 'x')).toBe('Network error. Please check your connection.')
    expect(store.notice).toBe('')
    expect(store.items).toHaveLength(1)
  })

  it('clears the notice on the next decision and on a tab switch', async () => {
    const store = await storeWith([item('r1', 'Ravi'), item('r2', 'Asha')])
    post.mockRejectedValueOnce(axios409('Cancelled by Ravi'))
    await store.approve('r1', '')
    post.mockResolvedValueOnce({ data: {} })
    await store.approve('r2', '')
    expect(store.notice).toBe('')

    post.mockRejectedValueOnce(axios409('Cancelled by Ravi'))
    await store.approve('r1', '')
    await store.fetch('decided')
    expect(store.notice).toBe('')
  })
})

describe('withdraw and reschedule', () => {
  it('shows the request as it now stands', async () => {
    const store = await storeWith([item('r1', 'Ravi')])
    post.mockResolvedValue({ data: { id: 'r1', status: 'withdrawn' } })
    expect(await store.withdraw('r1', '  Plans changed ')).toBeNull()
    expect(post).toHaveBeenCalledWith('/v1/leave/requests/r1/withdraw', { note: 'Plans changed' })
    expect(store.items[0].request).toEqual({ id: 'r1', status: 'withdrawn' })
  })

  it('sends a blank note as none, and explains a failure', async () => {
    const store = await storeWith([item('r1', 'Ravi')])
    post.mockRejectedValue(new Error('Network Error'))
    const dates = { start_date: '2026-11-03', end_date: '2026-11-04', half_day: 'none', note: '  ' }
    expect(await store.reschedule('r1', dates)).toBe('Network error. Please check your connection.')
    expect(post).toHaveBeenCalledWith('/v1/leave/requests/r1/reschedule', { ...dates, note: null })
    expect(store.items[0].request.id).toBe('r1')
  })
})

describe('fetch', () => {
  it('fills the pickers from the unfiltered queue, by name', async () => {
    const store = await storeWith([item('r1', 'Ravi', 'sick'), item('r2', 'Asha', null), item('r3', 'Ravi', 'casual')])
    expect(store.people.map(p => p.name)).toEqual(['Asha', 'Ravi'])
    expect(store.leaveTypes.map(t => t.id)).toEqual(['casual', 'sick'])

    // A filtered queue doesn't shrink the pickers.
    store.filters.user_id = 'u-Asha'
    get.mockResolvedValue({ data: { items: [item('r2', 'Asha', null)], truncated: false } })
    await store.fetch()
    expect(store.people.map(p => p.name)).toEqual(['Asha', 'Ravi'])
  })

  it('keeps the newest answer when an older fetch replies last', async () => {
    let answerOld: (v: unknown) => void = () => undefined
    get.mockImplementationOnce(() => new Promise(resolve => { answerOld = resolve }))
    get.mockResolvedValueOnce({ data: { items: [item('new', 'Asha')], truncated: true } })
    const store = useLeaveApprovalsStore()
    const older = store.fetch('pending')
    await store.fetch('decided')
    answerOld({ data: { items: [item('old', 'Ravi')], truncated: false } })
    await older
    expect(store.items.map(i => i.request.id)).toEqual(['new'])
    expect(store.truncated).toBe(true)
    expect(store.status).toBe('decided')
  })

  it('shows a reload hint when the queue fails to load', async () => {
    get.mockRejectedValue(Object.assign(new Error('500'), { response: { status: 500, data: {} } }))
    const store = useLeaveApprovalsStore()
    await store.fetch()
    expect(store.error).toBe("Couldn't load approvals. Reload to try again.")
    expect(store.loading).toBe(false)
  })
})
