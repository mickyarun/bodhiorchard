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
 * The dashboard's setup card: it polls until setup is done, follows a
 * running scan live, stays hidden once dismissed, and comes back when the
 * org is reset. Timers are faked; the socket and scan store are stubs.
 */
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h as render } from 'vue'
import type { SetupChecklistStatus } from '@/types/setup'

const h = vi.hoisted(() => ({
  get: vi.fn(),
  startTracking: vi.fn(),
  stopTracking: vi.fn(),
  scan: { aggregateStatus: 'idle', phases: [], ingestStatus: vi.fn(), resume: vi.fn() },
}))
vi.mock('@/services/api', () => ({ default: { get: h.get } }))
vi.mock('@/composables/useScanSocket', () => ({
  useScanSocket: () => ({ startTracking: h.startTracking, stopTracking: h.stopTracking }),
}))
vi.mock('@/stores/scan', () => ({ useScanStore: () => h.scan }))

import { useSetupChecklist } from '@/composables/useSetupChecklist'

const DISMISS_KEY = 'bodhiorchard_checklist_dismissed'
const DONE: SetupChecklistStatus = {
  orgCreated: true, claudeCodeTested: true, repoAdded: true, scanComplete: true,
  scanInProgress: false, scanId: null, scanProgress: 100, githubConnected: true,
  slackConnected: true, branchesMapped: true, membersImported: true, qaConfigured: true,
}

function status(over: Partial<SetupChecklistStatus>): SetupChecklistStatus {
  return { ...DONE, ...over }
}

async function mountCard() {
  let card!: ReturnType<typeof useSetupChecklist>
  const wrapper = mount(defineComponent({
    setup() { card = useSetupChecklist(); return () => render('div') },
  }))
  await flushPromises()
  return { card, wrapper }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  localStorage.clear()
  h.scan.aggregateStatus = 'idle'
})

enableAutoUnmount(afterEach)
afterEach(() => vi.useRealTimers())

describe('useSetupChecklist', () => {
  it('shows the next step and keeps polling while setup is unfinished', async () => {
    h.get.mockResolvedValue({ data: status({ slackConnected: false, membersImported: false, branchesMapped: false }) })
    const { card } = await mountCard()
    expect(card.visible.value).toBe(true)
    expect(card.nextStep.value?.done).toBe(false)
    expect(card.doneCount.value).toBe(card.steps.value.length - 3)
    await vi.advanceTimersByTimeAsync(10_000)
    expect(h.get).toHaveBeenCalledTimes(2)
  })

  it('stops polling once setup is done and hides with nothing left', async () => {
    h.get.mockResolvedValue({ data: DONE })
    const { card } = await mountCard()
    expect(card.visible.value).toBe(false)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(h.get).toHaveBeenCalledOnce()
  })

  it('stays hidden after dismissing, across a reload, and stops polling', async () => {
    h.get.mockResolvedValue({ data: status({ slackConnected: false }) })
    const first = await mountCard()
    first.card.dismiss()
    expect(first.card.visible.value).toBe(false)
    expect(localStorage.getItem(DISMISS_KEY)).toBe('true')
    first.wrapper.unmount()

    h.get.mockClear()
    const { card } = await mountCard()
    expect(card.visible.value).toBe(false)
    await vi.advanceTimersByTimeAsync(30_000)
    expect(h.get).toHaveBeenCalledOnce()
  })

  it('comes back after a dismissal once the org is reset', async () => {
    localStorage.setItem(DISMISS_KEY, 'true')
    h.get.mockResolvedValue({ data: status({ scanComplete: false }) })
    const { card } = await mountCard()
    expect(card.visible.value).toBe(true)
    expect(localStorage.getItem(DISMISS_KEY)).toBeNull()
  })

  it('follows a running scan live and refreshes when it finishes', async () => {
    h.get.mockResolvedValue({ data: status({ scanInProgress: true, scanId: 'scan-1', scanProgress: 10, scanComplete: false }) })
    const { card } = await mountCard()
    expect(h.startTracking).toHaveBeenCalledOnce()
    const [scanId, handlers] = h.startTracking.mock.calls[0]
    expect(scanId).toBe('scan-1')

    handlers.onProgress({ progressPct: 64, statusLabel: 'Indexing api', repoWarnings: [] })
    expect(card.scanning.value).toBe(true)
    expect(card.scanProgress.value).toBe(64)
    expect(card.scanLabel.value).toBe('Indexing api')
    expect(h.scan.ingestStatus).toHaveBeenCalled()

    h.get.mockResolvedValue({ data: DONE })
    handlers.onComplete()
    await flushPromises()
    expect(card.scanning.value).toBe(false)
    expect(card.visible.value).toBe(false)
  })

  it('tracks a scan once however often the poll sees it', async () => {
    h.get.mockResolvedValue({ data: status({ scanInProgress: true, scanId: 'scan-1', scanComplete: false }) })
    await mountCard()
    await vi.advanceTimersByTimeAsync(20_000)
    expect(h.startTracking).toHaveBeenCalledOnce()
  })

  it('reports a failed scan when nothing is running', async () => {
    h.scan.aggregateStatus = 'failed'
    h.get.mockResolvedValue({ data: status({ scanComplete: false }) })
    const { card } = await mountCard()
    expect(card.scanFailed.value).toBe(true)
  })

  it('does not report the last scan as failed while a new one runs', async () => {
    h.scan.aggregateStatus = 'failed'
    h.get.mockResolvedValue({ data: status({ scanComplete: false }) })
    h.scan.resume.mockResolvedValue('scan-2')
    const { card } = await mountCard()
    await card.resumeScan()
    expect(card.scanFailed.value).toBe(false)
  })

  it('keeps the last state when a poll fails', async () => {
    h.get.mockResolvedValueOnce({ data: status({ slackConnected: false }) })
    h.get.mockRejectedValueOnce(new Error('Network Error'))
    const { card } = await mountCard()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(card.visible.value).toBe(true)
  })

  it('resumes a scan and follows it', async () => {
    h.get.mockResolvedValue({ data: status({ scanComplete: false }) })
    h.scan.resume.mockResolvedValue('scan-2')
    const { card } = await mountCard()
    await card.resumeScan()
    expect(h.startTracking.mock.calls[0][0]).toBe('scan-2')
    expect(card.resuming.value).toBe(false)
  })

  it('stops polling and tracking when the card goes away', async () => {
    h.get.mockResolvedValue({ data: status({ slackConnected: false }) })
    const { wrapper } = await mountCard()
    wrapper.unmount()
    expect(h.stopTracking).toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(h.get).toHaveBeenCalledOnce()
  })
})
