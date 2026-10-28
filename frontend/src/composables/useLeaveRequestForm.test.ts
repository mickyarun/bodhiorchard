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
 * The leave request dialog's form: what it would send for each kind, the
 * debounced server preview (only the latest counts), the date clamps, and
 * when Send is allowed. Timers and "today" are faked.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, type EffectScope } from 'vue'
import type { LeavePreview, LeaveRequestCreate } from '@/types/leave'

const preview = vi.hoisted(() => vi.fn())
vi.mock('@/stores/leave', () => ({ useLeaveStore: () => ({ preview }) }))

import { useLeaveRequestForm } from '@/composables/useLeaveRequestForm'

const OK = { days: '1', problems: [] } as unknown as LeavePreview
let scope: EffectScope

function form() {
  scope = effectScope()
  return scope.run(() => useLeaveRequestForm())!
}

/** Let watchers run, then the 300 ms debounce, then the preview reply. */
async function previewSettles(): Promise<void> {
  await nextTick()
  await vi.advanceTimersByTimeAsync(300)
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(2026, 9, 28, 9, 0))
  preview.mockReset()
  preview.mockResolvedValue({ data: OK, error: '' })
})

afterEach(() => {
  scope.stop()
  vi.useRealTimers()
})

describe('payload', () => {
  it('needs a leave type for leave and a holiday for an optional holiday', async () => {
    const f = form()
    f.reset('leave')
    expect(f.payload.value).toBeNull()
    f.leaveTypeId.value = 'casual'
    expect(f.payload.value).toEqual({
      kind: 'leave', leave_type_id: 'casual', holiday_id: null,
      start_date: '2026-10-28', end_date: '2026-10-28', half_day: 'none', reason: null,
    })

    f.reset('optional_holiday')
    expect(f.payload.value).toBeNull()
    f.holidayId.value = 'diwali'
    f.halfDay.value = 'first_half'
    expect(f.payload.value).toMatchObject({ leave_type_id: null, holiday_id: 'diwali', half_day: 'none' })
  })

  it('sends WFH without a type, and a trimmed reason or none', () => {
    const f = form()
    f.reset('wfh')
    f.reason.value = '   '
    expect(f.payload.value).toMatchObject({ kind: 'wfh', leave_type_id: null, reason: null })
    f.reason.value = '  plumber visit '
    expect(f.payload.value?.reason).toBe('plumber visit')
  })
})

describe('dates', () => {
  it('pulls the end date up to a later start, and back to the start', async () => {
    const f = form()
    f.reset('wfh')
    f.startDate.value = '2026-11-03'
    await nextTick()
    expect(f.endDate.value).toBe('2026-11-03')
    f.endDate.value = '2026-11-01'
    await nextTick()
    expect(f.endDate.value).toBe('2026-11-03')
  })

  it('offers half days on a single day only', async () => {
    const f = form()
    f.reset('leave')
    await nextTick()
    f.leaveTypeId.value = 'casual'
    f.halfDay.value = 'second_half'
    expect(f.singleDay.value).toBe(true)
    expect(f.payload.value?.half_day).toBe('second_half')
    f.endDate.value = '2026-10-30'
    await nextTick()
    expect(f.singleDay.value).toBe(false)
    expect(f.halfDay.value).toBe('none')
  })
})

describe('preview', () => {
  it('waits for typing to stop and previews once', async () => {
    const f = form()
    f.reset('leave')
    f.leaveTypeId.value = 'casual'
    await nextTick()
    f.endDate.value = '2026-10-29'
    await nextTick()
    expect(f.previewing.value).toBe(true)
    await vi.advanceTimersByTimeAsync(299)
    expect(preview).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(1)
    expect(preview).toHaveBeenCalledOnce()
    expect((preview.mock.calls[0][0] as LeaveRequestCreate).end_date).toBe('2026-10-29')
    expect(f.preview.value).toEqual(OK)
    expect(f.canSend.value).toBe(true)
  })

  it('drops a reply that a newer edit overtook', async () => {
    let answerOld: (v: unknown) => void = () => undefined
    preview.mockImplementationOnce(() => new Promise(resolve => { answerOld = resolve }))
    const f = form()
    f.reset('wfh')
    await previewSettles()
    f.endDate.value = '2026-10-30'
    await nextTick()
    answerOld({ data: { days: '9', problems: [] }, error: '' })
    await previewSettles()
    expect(f.preview.value).toEqual(OK)
    expect(f.previewing.value).toBe(false)
  })

  it('does not re-run for a change of reason', async () => {
    const f = form()
    f.reset('wfh')
    await previewSettles()
    f.reason.value = 'dentist'
    await previewSettles()
    expect(preview).toHaveBeenCalledOnce()
  })

  it('previews again when reopened with the same choices', async () => {
    const f = form()
    f.reset('wfh')
    await previewSettles()
    f.reset('wfh')
    expect(f.preview.value).toBeNull()
    await previewSettles()
    expect(preview).toHaveBeenCalledTimes(2)
  })

  it('stops previewing an incomplete form', async () => {
    const f = form()
    f.reset('leave')
    await previewSettles()
    expect(preview).not.toHaveBeenCalled()
    expect(f.previewing.value).toBe(false)
    expect(f.canSend.value).toBe(false)
  })
})

describe('canSend', () => {
  it('is false while the server reports a problem', async () => {
    preview.mockResolvedValue({ data: { ...OK, problems: [{ code: 'overlap', message: 'Overlaps' }] }, error: '' })
    const f = form()
    f.reset('wfh')
    await previewSettles()
    expect(f.canSend.value).toBe(false)
  })

  it('is false when the preview failed', async () => {
    preview.mockResolvedValue({ data: null, error: "Couldn't check this request. Try again." })
    const f = form()
    f.reset('wfh')
    await previewSettles()
    expect(f.previewError.value).toBe("Couldn't check this request. Try again.")
    expect(f.canSend.value).toBe(false)
  })
})
