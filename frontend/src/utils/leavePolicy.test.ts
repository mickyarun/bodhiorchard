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

import {
  DETAIL_FIELDS,
  mergePolicyFields,
  movedSummary,
  movedVariant,
  newPolicy,
  RULE_FIELDS,
  samePolicyFields,
} from '@/utils/leavePolicy'
import { timezoneOptions } from '@/utils/timezones'

describe('policy field groups', () => {
  it('never overlap, so two forms never fight over a field', () => {
    const overlap = DETAIL_FIELDS.filter(field => RULE_FIELDS.includes(field))
    expect(overlap).toEqual([])
  })

  it('compares only the fields a form owns', () => {
    const base = { ...newPolicy(), name: 'India' }
    const renamed = { ...base, name: 'India HQ' }
    expect(samePolicyFields(base, renamed, RULE_FIELDS)).toBe(true)
    expect(samePolicyFields(base, renamed, DETAIL_FIELDS)).toBe(false)
    expect(samePolicyFields(base, { ...base, working_days: [0, 1, 2] }, RULE_FIELDS)).toBe(false)
  })

  it('merges a form over the latest policy without undoing other edits', () => {
    const latest = { ...newPolicy(), name: 'Renamed elsewhere' }
    const rulesDraft = { ...newPolicy(), name: 'Stale name', backdate_limit_days: 30 }
    const body = mergePolicyFields(latest, rulesDraft, RULE_FIELDS)
    expect(body.name).toBe('Renamed elsewhere')
    expect(body.backdate_limit_days).toBe(30)
  })

  it('copies arrays so later edits do not leak into the body', () => {
    const draft = { ...newPolicy(), working_days: [0, 1] }
    const body = mergePolicyFields(newPolicy(), draft, RULE_FIELDS)
    draft.working_days.push(2)
    expect(body.working_days).toEqual([0, 1])
  })
})

describe('movedSummary', () => {
  it('names the policy and flags pending requests', () => {
    expect(movedSummary({ assigned: 1, pending_elsewhere: 0 }, 'UK Office')).toBe(
      'Moved 1 person to UK Office.',
    )
    expect(movedSummary({ assigned: 3, pending_elsewhere: 2 })).toMatch(
      /^Moved 3 people to this policy\. 2 of them have requests still pending/,
    )
  })

  it('says so when nobody needed moving', () => {
    expect(movedSummary({ assigned: 0, pending_elsewhere: 0 }, 'UK Office')).toBe(
      'Nobody moved: everyone selected already follows UK Office.',
    )
  })
})

describe('movedVariant', () => {
  it('warns when requests are still pending elsewhere', () => {
    expect(movedVariant({ assigned: 2, pending_elsewhere: 0 })).toBe('success')
    expect(movedVariant({ assigned: 2, pending_elsewhere: 1 })).toBe('warning')
  })
})

describe('timezoneOptions', () => {
  it('includes UTC and the saved value, sorted and unique', () => {
    expect(timezoneOptions('Mars/Base', ['Europe/London', 'Asia/Kolkata', 'Europe/London'])).toEqual([
      'Asia/Kolkata',
      'Europe/London',
      'Mars/Base',
      'UTC',
    ])
  })
})
