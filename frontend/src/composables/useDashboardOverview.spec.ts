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
 * The dashboard overview: who sees the BUD cards, the approver's queue
 * size, upcoming time off (the next three weeks, leave only, soonest
 * first) and each card's error. "Today" is frozen.
 */
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h as render, reactive } from 'vue'

const h = vi.hoisted(() => ({
  get: vi.fn(),
  permissions: [] as string[],
  bud: { buds: [] as unknown[], loading: false, error: '', fetchBUDs: vi.fn() },
  leave: {
    approvalCount: { pending: 0, is_approver: false, has_reports: false },
    fetchApprovalCount: vi.fn(),
  },
  settings: { connectionsLoaded: false, connections: {} as Record<string, unknown>, fetchConnections: vi.fn() },
}))
vi.mock('@/services/api', () => ({ default: { get: h.get } }))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: { role: 'developer', permissions: h.permissions } }),
}))
vi.mock('@/stores/bud', () => ({ useBUDStore: () => h.bud }))
vi.mock('@/stores/leave', () => ({ useLeaveStore: () => h.leave }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => h.settings }))

import { useDashboardOverview } from '@/composables/useDashboardOverview'

function entry(id: string, start: string, kind = 'leave', status = 'approved') {
  return { request_id: id, kind, status, start_date: start, end_date: start }
}

async function mountOverview(): Promise<ReturnType<typeof useDashboardOverview>> {
  let overview!: ReturnType<typeof useDashboardOverview>
  mount(defineComponent({ setup() { overview = useDashboardOverview(); return () => render('div') } }))
  await flushPromises()
  return overview
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 9, 28, 10, 0))
  vi.clearAllMocks()
  h.permissions = ['buds:view', 'integrations:view']
  h.bud = reactive({ buds: [], loading: false, error: '', fetchBUDs: vi.fn(async () => undefined) })
  h.leave.approvalCount = { pending: 0, is_approver: false, has_reports: false }
  h.settings.connectionsLoaded = false
  h.settings.connections = reactive({ budStages: { uatEnabled: true } })
  h.get.mockResolvedValue({ data: { entries: [] } })
})

enableAutoUnmount(afterEach)
afterEach(() => vi.useRealTimers())

describe('useDashboardOverview', () => {
  it('loads the BUDs, the stage settings, the approvals badge and time off', async () => {
    await mountOverview()
    expect(h.bud.fetchBUDs).toHaveBeenCalledOnce()
    expect(h.settings.fetchConnections).toHaveBeenCalledOnce()
    expect(h.leave.fetchApprovalCount).toHaveBeenCalledOnce()
    expect(h.get).toHaveBeenCalledWith('/v1/leave/calendar', {
      params: { start: '2026-10-28', end: '2026-11-18' },
    })
  })

  it('shows only the people cards to someone without buds:view', async () => {
    h.permissions = []
    const o = await mountOverview()
    expect(o.canViewBuds.value).toBe(false)
    expect(h.bud.fetchBUDs).not.toHaveBeenCalled()
    expect(h.settings.fetchConnections).not.toHaveBeenCalled()
    expect(h.get).toHaveBeenCalled()
  })

  it('reports the BUD list failing to load', async () => {
    h.bud.fetchBUDs.mockImplementation(async () => { h.bud.error = 'Failed to load BUDs' })
    const o = await mountOverview()
    expect(o.error.value).toBe('Failed to load BUDs')
  })

  it('counts work and people in flight, leaving ended BUDs out', async () => {
    h.bud.buds = [
      { id: '1', status: 'development', assignee_id: 'ana', priority: 'P2', open_bug_count: 0 },
      { id: '2', status: 'testing', assignee_id: 'ana', priority: 'P2', open_bug_count: 2 },
      { id: '3', status: 'design', assignee_id: null, priority: 'P2', open_bug_count: 0 },
      { id: '4', status: 'closed', assignee_id: 'raj', priority: 'P2', open_bug_count: 5 },
    ]
    const o = await mountOverview()
    expect(o.inFlightCount.value).toBe(3)
    expect(o.peopleInFlight.value).toBe(1)
    expect(o.kpis.value.at(-1)).toMatchObject({ label: 'Open bugs', value: 2 })
  })

  it('puts the leave queue in place of open bugs for approvers only', async () => {
    h.leave.approvalCount = { pending: 3, is_approver: true, has_reports: true }
    const o = await mountOverview()
    expect(o.pendingLeave.value).toBe(3)
    expect(o.kpis.value.at(-1)).toMatchObject({ label: 'Leave requests', value: 3 })
  })

  it('shows null, not zero, for someone who approves nothing', async () => {
    h.leave.approvalCount = { pending: 4, is_approver: false, has_reports: false }
    expect((await mountOverview()).pendingLeave.value).toBeNull()
  })

  it('lists approved and pending leave only, soonest first, four at most', async () => {
    h.get.mockResolvedValue({ data: { entries: [
      entry('wfh', '2026-10-29', 'wfh'),
      entry('rejected', '2026-10-29', 'leave', 'rejected'),
      entry('late', '2026-11-10'),
      entry('pending', '2026-11-02', 'leave', 'pending'),
      entry('soon', '2026-10-30'),
      entry('holiday', '2026-11-05', 'optional_holiday'),
      entry('later', '2026-11-12'),
    ] } })
    const o = await mountOverview()
    expect(o.timeOff.value.map(e => e.request_id)).toEqual(['soon', 'pending', 'holiday', 'late'])
    expect(o.timeOffError.value).toBe('')
  })

  it("says time off didn't load and shows none", async () => {
    h.get.mockRejectedValue(new Error('Network Error'))
    const o = await mountOverview()
    expect(o.timeOff.value).toEqual([])
    expect(o.timeOffError.value).toBe('Network error. Please check your connection.')
  })

  it('does not refetch connections already loaded', async () => {
    h.settings.connectionsLoaded = true
    await mountOverview()
    expect(h.settings.fetchConnections).not.toHaveBeenCalled()
  })

  it('shows the loading state only before any BUD has arrived', async () => {
    const o = await mountOverview()
    h.bud.loading = true
    expect(o.loading.value).toBe(true)
    h.bud.buds = [{ id: '1', status: 'bud', assignee_id: null, priority: 'P2', open_bug_count: 0 }]
    expect(o.loading.value).toBe(false)
  })
})
