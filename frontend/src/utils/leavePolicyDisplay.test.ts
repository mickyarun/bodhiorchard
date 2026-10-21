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

import type { LeaveTypeRead, PolicyRead } from '@/types/leavePolicy'
import { newPolicy } from '@/utils/leavePolicy'
import {
  allowanceLabel,
  deleteBlocker,
  holidaySummary,
  parseSection,
  peopleCount,
  policyStatLine,
  splitLeaveTypes,
  SWATCH_OPTIONS,
  wfhRuleCaption,
  workWeekLabel,
} from '@/utils/leavePolicyDisplay'

function policy(overrides: Partial<PolicyRead> = {}): PolicyRead {
  return {
    ...newPolicy(),
    name: 'India',
    id: 'p1',
    is_default: false,
    employee_count: 0,
    has_requests: false,
    ...overrides,
  }
}

function type(overrides: Partial<LeaveTypeRead> = {}): LeaveTypeRead {
  return {
    id: 't1',
    policy_id: 'p1',
    name: 'Casual',
    code: 'CL',
    annual_quota_days: '12',
    accrual: 'upfront',
    is_encashable: false,
    counts_toward_warning: true,
    eligibility: 'everyone',
    auto_approve: false,
    monthly_limit_days: null,
    is_paid: true,
    color_key: 'swatch-1',
    is_active: true,
    ...overrides,
  }
}

describe('workWeekLabel', () => {
  it('collapses a run of days into a range', () => {
    expect(workWeekLabel([0, 1, 2, 3, 4])).toBe('Mon–Fri')
    expect(workWeekLabel([5, 0, 1, 2, 3, 4])).toBe('Mon–Sat')
  })

  it('lists days that are not a run', () => {
    expect(workWeekLabel([0, 2, 4])).toBe('Mon, Wed, Fri')
    expect(workWeekLabel([5, 6])).toBe('Sat, Sun')
  })

  it('names the edges', () => {
    expect(workWeekLabel([0, 1, 2, 3, 4, 5, 6])).toBe('Every day')
    expect(workWeekLabel([])).toBe('No working days')
  })
})

describe('policyStatLine', () => {
  it('reads people, work week and leave year', () => {
    const line = policyStatLine(policy({ employee_count: 12, year_start_month: 4 }))
    expect(line).toBe('12 people · Mon–Fri · Year starts April')
  })

  it('uses the singular for one person', () => {
    expect(peopleCount(1)).toBe('1 person')
  })
})

describe('wfhRuleCaption', () => {
  it('describes each approval mode', () => {
    expect(wfhRuleCaption({ wfh_approval: 'required', wfh_monthly_auto_days: 0 })).toBe(
      'Work from home always needs approval',
    )
    expect(wfhRuleCaption({ wfh_approval: 'auto', wfh_monthly_auto_days: 0 })).toBe(
      'Work from home is approved automatically',
    )
    expect(wfhRuleCaption({ wfh_approval: 'auto_within_allowance', wfh_monthly_auto_days: 4 })).toBe(
      'Work from home is approved automatically up to 4 days a month',
    )
  })
})

describe('deleteBlocker', () => {
  it('explains why a policy stays', () => {
    expect(deleteBlocker(policy({ is_default: true }))).toBe('Make another policy the default first')
    expect(deleteBlocker(policy({ employee_count: 2 }))).toBe('Move its people off first')
    expect(deleteBlocker(policy({ has_requests: true }))).toMatch(/requested/)
  })

  it('allows an unused policy', () => {
    expect(deleteBlocker(policy())).toBeNull()
  })
})

describe('leave types', () => {
  it('labels the allowance', () => {
    expect(allowanceLabel(type())).toBe('12 days')
    expect(allowanceLabel(type({ annual_quota_days: '0.5' }))).toBe('0.5 days')
    expect(allowanceLabel(type({ annual_quota_days: null }))).toBe('Unlimited')
    expect(allowanceLabel(type({ annual_quota_days: '18', accrual: 'monthly' }))).toBe(
      '18 days, earned monthly',
    )
  })

  it('keeps switched-off types apart', () => {
    const { active, inactive } = splitLeaveTypes([
      type({ id: 'a' }),
      type({ id: 'b', is_active: false }),
      type({ id: 'c' }),
    ])
    expect(active.map(t => t.id)).toEqual(['a', 'c'])
    expect(inactive.map(t => t.id)).toEqual(['b'])
  })

  it('names every swatch', () => {
    expect(SWATCH_OPTIONS.map(s => s.name)).toEqual([
      'Green',
      'Blue',
      'Amber',
      'Red',
      'Gold',
      'Teal',
      'Grey',
    ])
  })
})

describe('parseSection', () => {
  it('accepts known sections and falls back to leave types', () => {
    expect(parseSection('rules')).toBe('rules')
    expect(parseSection('general')).toBe('types')
    expect(parseSection(undefined)).toBe('types')
  })
})

describe('holidaySummary', () => {
  it('counts holidays and optional ones', () => {
    expect(holidaySummary([])).toBe('No holidays yet')
    expect(holidaySummary([{ kind: 'mandatory' }])).toBe('1 holiday')
    expect(
      holidaySummary([{ kind: 'mandatory' }, { kind: 'optional' }, { kind: 'mandatory' }]),
    ).toBe('3 holidays, 1 optional')
  })
})
