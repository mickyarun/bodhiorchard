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

/** The approvals store forgets a previous viewer's filters and picker names. */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn() } }))
// The real auth store reads localStorage on start; only `user` matters here.
const auth = vi.hoisted(() => ({ user: null as { id: string } | null }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

import api from '@/services/api'
import { useLeaveApprovalsStore } from '@/stores/leaveApprovals'

const get = vi.mocked(api.get)

function signIn(id: string): void {
  auth.user = { id }
}

beforeEach(() => {
  setActivePinia(createPinia())
  get.mockReset()
  get.mockResolvedValue({ data: { items: [], truncated: false } })
})

describe('forgetPreviousViewer', () => {
  it("clears another viewer's filters and pickers, but keeps your own", async () => {
    const store = useLeaveApprovalsStore()
    signIn('hr')
    await store.fetch()
    Object.assign(store.filters, { user_id: 'someone', kind: 'leave' })
    store.people = [{ user_id: 'someone', name: 'Someone' }]
    await store.fetch()
    expect(store.filters.user_id).toBe('someone')

    signIn('manager')
    await store.fetch()
    expect(store.filters).toEqual({ start: '', end: '', kind: null, leave_type_id: null, user_id: null })
    expect(store.people).toEqual([])
  })
})

describe('fetch with a reversed range', () => {
  it("explains the problem and doesn't call the API", async () => {
    signIn('hr')
    const store = useLeaveApprovalsStore()
    await store.fetch()
    get.mockClear()
    Object.assign(store.filters, { start: '2026-06-10', end: '2026-06-01' })
    await store.fetch()
    expect(store.error).toMatch(/on or after/)
    expect(get).not.toHaveBeenCalled()
  })
})
