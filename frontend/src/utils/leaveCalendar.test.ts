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

import { describe, expect, it } from 'vitest'

import type { CalendarEntry } from '@/types/leave'
import { entriesOnDay, monthSummary } from '@/utils/leaveCalendar'

function entry(id: string, over: Partial<CalendarEntry>): CalendarEntry {
  return {
    request_id: id,
    user: { user_id: id, name: id },
    kind: 'leave',
    start_date: '2026-11-02',
    end_date: '2026-11-02',
    half_day: 'none',
    status: 'approved',
    is_own: false,
    leave_type: null,
    reason: null,
    working_days: [0, 1, 2, 3, 4],
    ...over,
  }
}

const NOVEMBER = { year: 2026, month: 11 }

describe('monthSummary', () => {
  it('counts distinct people out and working from home in the month', () => {
    const text = monthSummary(
      [
        entry('a', {}),
        entry('a', { start_date: '2026-11-20', end_date: '2026-11-20' }),
        entry('b', { start_date: '2026-10-30', end_date: '2026-11-03', status: 'pending' }),
        entry('c', { kind: 'wfh' }),
        entry('d', { status: 'rejected' }),
        entry('e', { start_date: '2026-12-01', end_date: '2026-12-02' }),
      ],
      NOVEMBER,
    )
    expect(text).toBe('2 people out in November · 1 working from home')
  })

  it('is empty when nobody is out', () => {
    expect(monthSummary([], NOVEMBER)).toBe('')
  })

  it('uses the singular for one person', () => {
    expect(monthSummary([entry('a', {})], NOVEMBER)).toBe('1 person out in November')
  })
})

describe('entriesOnDay', () => {
  it('skips the owner’s days off and puts leave before WFH', () => {
    const list = entriesOnDay(
      [
        entry('wfh', { kind: 'wfh', start_date: '2026-11-06', end_date: '2026-11-06' }),
        entry('leave', { start_date: '2026-11-02', end_date: '2026-11-08' }),
      ],
      '2026-11-06',
    )
    expect(list.map(e => e.request_id)).toEqual(['leave', 'wfh'])
    // Sat 7 Nov is a day off for both.
    expect(entriesOnDay([entry('leave', { start_date: '2026-11-02', end_date: '2026-11-08' })], '2026-11-07')).toEqual([])
  })
})
