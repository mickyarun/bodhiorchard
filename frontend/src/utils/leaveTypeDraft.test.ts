/**
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { describe, expect, it } from 'vitest'
import type { LeaveTypeRead } from '@/types/leavePolicy'
import { monthlyLimitNote } from '@/utils/leaveAccrual'
import { changeLines } from '@/utils/leaveConfigHistory'
import { typeRuleTags } from '@/utils/leavePolicyDisplay'
import { blankType, draftFromType, hasWomenOnlyType, periodLeave, validMonthlyLimit } from '@/utils/leaveTypeDraft'

const read = (over: Partial<LeaveTypeRead> = {}): LeaveTypeRead => ({
  ...blankType(),
  name: 'Casual',
  code: 'CL',
  id: 't1',
  policy_id: 'p1',
  ...over,
})

describe('leave type drafts', () => {
  it('starts period leave as women only, self-approving, one day a month', () => {
    const period = periodLeave()
    expect(period).toMatchObject({
      name: 'Period leave',
      annual_quota_days: 12,
      eligibility: 'women',
      auto_approve: true,
      monthly_limit_days: 1,
      counts_toward_warning: false,
      is_encashable: false,
      is_paid: true,
    })
  })

  it('drops ids when editing an existing type', () => {
    const draft = draftFromType(read())
    expect(draft).not.toHaveProperty('id')
    expect(draft).not.toHaveProperty('policy_id')
  })

  it('knows when a policy already has a women-only type', () => {
    expect(hasWomenOnlyType([read()])).toBe(false)
    expect(hasWomenOnlyType([read(), read({ eligibility: 'women' })])).toBe(true)
  })
})

describe('type rule tags and history', () => {
  it('lists only the special rules', () => {
    expect(typeRuleTags(read())).toEqual([])
    expect(typeRuleTags(read({ ...periodLeave() }))).toEqual(['Women only', 'Auto-approved', '1 day a month'])
  })

  it('reads the new fields in the change log', () => {
    expect(
      changeLines({ eligibility: ['everyone', 'women'], auto_approve: [false, true], monthly_limit_days: [null, '1.0'] }),
    ).toEqual(['Who can use it: everyone → women only', 'Approved automatically: no → yes', 'Most days in a month: 1'])
  })
})

describe('monthlyLimitNote', () => {
  it('says the per-month limit, or nothing', () => {
    expect(monthlyLimitNote({ monthly_limit_days: '1.0' })).toBe('Up to 1 day a month; unused days lapse.')
    expect(monthlyLimitNote({ monthly_limit_days: null })).toBe('')
    expect(monthlyLimitNote({})).toBe('')
  })
})

describe('validMonthlyLimit', () => {
  it('accepts no limit or half-day steps up to 31', () => {
    expect(validMonthlyLimit(null)).toBe(true)
    expect(validMonthlyLimit(1)).toBe(true)
    expect(validMonthlyLimit('1.5')).toBe(true)
    expect(validMonthlyLimit('')).toBe(false)
    expect(validMonthlyLimit(0)).toBe(false)
    expect(validMonthlyLimit(0.25)).toBe(false)
    expect(validMonthlyLimit(40)).toBe(false)
  })
})
