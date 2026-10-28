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

import type { ConfigEventRead } from '@/types/leavePolicy'
import { changeLines, eventTitle, recalculationSummary } from '@/utils/leaveConfigHistory'

const event = (action: ConfigEventRead['action'], changes: Record<string, unknown> = {}) =>
  ({
    id: 'e1',
    action,
    actor: { user_id: 'u1', name: 'Priya' },
    at: '2026-10-19T09:00:00Z',
    changes,
  }) satisfies ConfigEventRead

describe('changeLines', () => {
  it('names the library a type follows, or that it stopped', () => {
    expect(changeLines({ type: 'SL', library: [null, 'Sick'], own_quota: [false, true] })).toEqual([
      'Library type: Sick',
      "Policy's own yearly quota: no → yes",
    ])
    expect(changeLines({ library: ['Sick', null] })).toEqual([
      "Library type: Sick → none (the policy's own)",
    ])
  })

  it('describes each changed field in plain words', () => {
    expect(
      changeLines({
        type: 'CL',
        annual_quota_days: ['12', '15'],
        proration_method: ['daily', 'monthly'],
        working_days: [
          [0, 1, 2, 3, 4],
          [0, 1, 2, 3, 4, 5],
        ],
      }),
    ).toEqual([
      'Yearly quota: 12 → 15',
      'Prorate new joiners: daily → monthly',
      'Working days: Mon, Tue, Wed, Thu, Fri → Mon, Tue, Wed, Thu, Fri, Sat',
    ])
  })

  it('names how a type is given and whether it is encashable', () => {
    expect(changeLines({ accrual: ['upfront', 'monthly'], is_encashable: [false, true] })).toEqual([
      'Given: all at once → monthly',
      'Encashable at exit: no → yes',
    ])
  })

  it('ignores fields that are not changes, like assigned ids', () => {
    expect(changeLines({ user_ids: ['a', 'b'], assigned: 2 })).toEqual([])
  })

  it('shows a new value alone, and an unlimited quota as "no limit"', () => {
    expect(changeLines({ annual_quota_days: [null, null], name: [null, 'India'] })).toEqual([
      'Yearly quota: no limit',
      'Name: India',
    ])
    expect(changeLines({ annual_quota_days: ['12', null] })).toEqual([
      'Yearly quota: 12 → no limit',
    ])
    expect(changeLines({ annual_quota_days: ['7.0', '8'] })).toEqual(['Yearly quota: 7 → 8'])
  })
})

describe('eventTitle', () => {
  it('names the leave type and counts people moved', () => {
    expect(eventTitle(event('type_updated', { type: 'CL' }))).toBe('Changed leave type CL')
    expect(eventTitle(event('type_updated', { type: 'SL', library: 'Sick' }))).toBe(
      'Changed leave type SL in the library',
    )
    expect(eventTitle(event('type_updated', { type: 'SL', library: [null, 'Sick'] }))).toBe(
      'Changed leave type SL',
    )
    expect(eventTitle(event('library_type_created', { library: 'Sick' }))).toBe('Added library type Sick')
    expect(eventTitle(event('library_type_updated', { library: 'Sick leave' }))).toBe(
      'Changed library type Sick leave',
    )
    expect(eventTitle(event('library_type_deleted', { library: 'Sick' }))).toBe('Deleted library type Sick')
    expect(eventTitle(event('employees_assigned', { assigned: 1 }))).toBe(
      'Moved 1 person onto this policy',
    )
    expect(eventTitle(event('employees_assigned', { assigned: 3 }))).toBe(
      'Moved 3 people onto this policy',
    )
  })
})

describe('recalculationSummary', () => {
  it('says what was booked, or that the allocation already matches', () => {
    expect(recalculationSummary({ frozen: '12', recalculated: '6.5', correction: '-5.5' })).toBe(
      'Was 12 days, now 6.5: booked −5.5 days.',
    )
    expect(recalculationSummary({ frozen: '6', recalculated: '6', correction: '0' })).toBe(
      'The allocation already matches the current rules.',
    )
  })
})
