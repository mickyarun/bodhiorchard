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

import type { CalendarEntry, LeaveSummary } from '@/types/leave'
import { approversOf, dateBadge, outSoon, policyNotes } from '@/utils/leaveHome'

function entry(over: Partial<CalendarEntry>): CalendarEntry {
  return {
    request_id: over.request_id ?? 'r1',
    user: { user_id: 'u1', name: 'Neha Sharma' },
    kind: 'leave',
    start_date: '2026-10-28',
    end_date: '2026-10-28',
    half_day: 'none',
    status: 'approved',
    is_own: false,
    leave_type: null,
    reason: null,
    working_days: [0, 1, 2, 3, 4],
    ...over,
  }
}

describe('outSoon', () => {
  const today = '2026-10-28'

  it('keeps other people out in the window, soonest first', () => {
    const { rows, more } = outSoon(
      [
        entry({ request_id: 'b', start_date: '2026-11-02', end_date: '2026-11-06', user: { user_id: 'u2', name: 'Tom' } }),
        entry({ request_id: 'a', kind: 'wfh', status: 'pending', start_date: '2026-10-29', end_date: '2026-10-29' }),
        entry({ request_id: 'own', is_own: true }),
        entry({ request_id: 'gone', status: 'rejected' }),
        entry({ request_id: 'past', start_date: '2026-10-20', end_date: '2026-10-27' }),
        entry({ request_id: 'late', start_date: '2026-11-04', end_date: '2026-11-04' }),
      ],
      today,
      7,
      5,
    )
    expect(rows.map(r => r.id)).toEqual(['a', 'b'])
    expect(more).toBe(0)
    expect(rows[0]).toMatchObject({ label: 'WFH', pending: true })
    expect(rows[1]).toMatchObject({ label: 'Leave', pending: false, name: 'Tom' })
  })

  it('includes leave already under way, caps the list and counts the rest', () => {
    const { rows, more } = outSoon(
      [entry({ request_id: 'x', start_date: '2026-10-26', end_date: '2026-10-30' }), entry({ request_id: 'y' })],
      today,
      7,
      1,
    )
    expect(rows.map(r => r.id)).toEqual(['x'])
    expect(more).toBe(1)
  })
})

describe('dateBadge', () => {
  it('splits a date into month and day', () => {
    expect(dateBadge('2026-12-21')).toEqual({ month: 'Dec', day: '21' })
  })
})

describe('policyNotes', () => {
  const summary = {
    policy: { wfh_approval: 'auto_within_allowance', wfh_monthly_auto_days: 2, backdate_limit_days: 30 },
    approvers: [{ user_id: 'm', name: 'Daniel Okafor' }],
    routes_to_hr: false,
    work_arrangement: 'office',
  } as unknown as LeaveSummary

  it('names the approvers and the WFH and backdating rules', () => {
    expect(policyNotes(summary)).toEqual([
      'Requests that need approval go to Daniel Okafor.',
      'Up to 2 days of work from home a month are approved automatically.',
      'Requests can go back up to 30 days.',
      "If a request needs more days than you have left, you'll see that before you send it.",
    ])
  })

  it('says HR when the policy routes there, and skips WFH for remote people', () => {
    const notes = policyNotes({ ...summary, routes_to_hr: true, work_arrangement: 'remote' } as LeaveSummary)
    expect(notes[0]).toBe('Requests that need approval go to HR.')
    expect(notes.some(n => n.includes('work from home'))).toBe(false)
  })
})

describe('approversOf', () => {
  const base = { approvers: [{ user_id: 'a', name: 'A' }, { user_id: 'b', name: 'B' }], routes_to_hr: false }

  it('names the approvers', () => {
    expect(approversOf(base as unknown as LeaveSummary)).toBe('A and B')
  })

  it('says HR when routed there, with nobody set, or before the summary loads', () => {
    expect(approversOf({ ...base, routes_to_hr: true } as unknown as LeaveSummary)).toBe('HR')
    expect(approversOf({ ...base, approvers: [] } as unknown as LeaveSummary)).toBe('HR')
    expect(approversOf(null)).toBe('HR')
  })
})
