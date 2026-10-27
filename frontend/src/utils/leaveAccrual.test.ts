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

import type { Balance } from '@/types/leave'
import {
  BOOKED_AHEAD_NOTE,
  bookedAheadNote,
  daysLeftForDraft,
  earnedSoFar,
  earningCaption,
} from '@/utils/leaveAccrual'

describe('earnedSoFar', () => {
  it('says how much of a monthly allowance is earned so far', () => {
    expect(earnedSoFar({ accrual: 'monthly', allocated: '18.0', earned: '15.0' })).toBe(
      'Earned 15 of 18 so far',
    )
    expect(earnedSoFar({ accrual: 'monthly', allocated: '8', earned: '6.6' })).toBe(
      'Earned 6.6 of 8 so far',
    )
  })

  it('stays quiet once it is all earned, for upfront types and with no limit', () => {
    expect(earnedSoFar({ accrual: 'monthly', allocated: '18', earned: '18' })).toBe('')
    expect(earnedSoFar({ accrual: 'upfront', allocated: '12', earned: '12' })).toBe('')
    expect(earnedSoFar({ accrual: 'monthly', allocated: null, earned: null })).toBe('')
  })
})

function balance(overrides: Partial<Balance>): Balance {
  return {
    leave_type: { id: 't1', name: 'Casual', code: 'CL', color_key: 'swatch-1' },
    is_paid: true,
    accrual: 'monthly',
    allocated: '12',
    earned: '10',
    adjustments: '0',
    added: '0',
    used: '2',
    pending: '0',
    available: '8',
    ...overrides,
  }
}

describe('earningCaption', () => {
  it('leads with what is earned and leaves out the yearly total', () => {
    expect(earningCaption(balance({}))).toBe('Earned 10 of 12 so far · 2 used')
    expect(earningCaption(balance({ pending: '1.5' }))).toBe(
      'Earned 10 of 12 so far · 2 used · 1.5 pending',
    )
  })

  it('hands back to the usual caption once everything is earned', () => {
    expect(earningCaption(balance({ earned: '12' }))).toBeNull()
    expect(earningCaption(balance({ accrual: 'upfront', earned: '12' }))).toBeNull()
  })
})

describe('bookedAheadNote', () => {
  it('explains days left that count what later months will earn', () => {
    // 10 earned, 3 pending in November: 8 left, not 10 - 3 = 7.
    const ahead = balance({ earned: '10', used: '0', pending: '3', available: '8' })
    expect(bookedAheadNote(ahead)).toBe(BOOKED_AHEAD_NOTE)
  })

  it('stays quiet when the numbers add up as they are', () => {
    expect(bookedAheadNote(balance({ earned: '10', used: '2', pending: '0', available: '8' }))).toBe('')
    expect(
      bookedAheadNote(balance({ accrual: 'upfront', earned: '12', pending: '3', available: '9' })),
    ).toBe('')
    expect(bookedAheadNote(balance({ earned: null, available: null }))).toBe('')
  })

  it('stays quiet after days are taken away with nothing booked', () => {
    // 3 earned by March, 2 taken off the year's total: still 3 left now.
    const deducted = balance({ earned: '3', adjustments: '-2', added: '0', used: '0', available: '3' })
    expect(bookedAheadNote(deducted)).toBe('')
  })
})

describe('daysLeftForDraft', () => {
  const casual = { leave_type: { id: 'cl' }, available: '0' } as Balance

  it("reads today's balance until the dates are priced", () => {
    expect(daysLeftForDraft(casual, null)).toBe('0')
    expect(daysLeftForDraft(casual, { balances_on_start: {} })).toBe('0')
  })

  it('reads the start-date balance the preview prices against, once there is one', () => {
    // A monthly type earns another day by December: the picker says so too.
    const preview = { balances_on_start: { cl: '1.0', sl: null } }
    expect(daysLeftForDraft(casual, preview)).toBe('1.0')
    const sick = { leave_type: { id: 'sl' }, available: '3' } as Balance
    expect(daysLeftForDraft(sick, preview)).toBeNull()
  })
})
