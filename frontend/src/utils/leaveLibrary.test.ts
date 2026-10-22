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

import type { LibraryTypeRead, LibraryTypeUse } from '@/types/leaveLibrary'
import type { LeaveTypeRead } from '@/types/leavePolicy'
import {
  entryBody,
  entryDraft,
  libraryChoices,
  linkBody,
  nameKey,
  quotaChoice,
  useLabel,
  usesLabel,
  validLinkQuota,
} from '@/utils/leaveLibrary'
import { blankType } from '@/utils/leaveTypeDraft'

const entry = (id: string, name: string, code: string): LibraryTypeRead => ({
  ...blankType(),
  name,
  code,
  annual_quota_days: '4.0',
  id,
  uses: [],
})

const policyType = (name: string, code: string, template_id: string | null = null): LeaveTypeRead => ({
  ...blankType(),
  name,
  code,
  id: `t-${code}`,
  policy_id: 'p1',
  template_id,
  own_quota: false,
})

const use = (over: Partial<LibraryTypeUse> = {}): LibraryTypeUse => ({
  policy_id: 'p1',
  policy_name: 'UK – London',
  type_id: 't1',
  own_quota: false,
  annual_quota_days: '4.0',
  is_active: true,
  ...over,
})

describe('nameKey', () => {
  it('ignores case and spacing, as the backend does', () => {
    expect(nameKey('  Sick   Leave ')).toBe(nameKey('sick leave'))
    expect(nameKey('Earned leave')).not.toBe(nameKey('Earned'))
  })
})

describe('quota choice', () => {
  it('reads where a linked type gets its quota from', () => {
    expect(quotaChoice({ own_quota: false, annual_quota_days: '4.0' })).toBe('library')
    expect(quotaChoice({ own_quota: true, annual_quota_days: '6.0' })).toBe('fixed')
    expect(quotaChoice({ own_quota: true, annual_quota_days: null })).toBe('unlimited')
  })

  it('saves only an own fixed quota as days', () => {
    expect(linkBody('library', 9, true)).toEqual({ own_quota: false, annual_quota_days: null, is_active: true })
    expect(linkBody('fixed', 6, false)).toEqual({ own_quota: true, annual_quota_days: 6, is_active: false })
    expect(linkBody('unlimited', 6, true)).toEqual({ own_quota: true, annual_quota_days: null, is_active: true })
  })

  it('accepts whole or half days up to a year for an own quota', () => {
    expect(validLinkQuota('fixed', 6.5)).toBe(true)
    expect(validLinkQuota('fixed', 6.3)).toBe(false)
    expect(validLinkQuota('fixed', null)).toBe(false)
    expect(validLinkQuota('fixed', 400)).toBe(false)
    expect(validLinkQuota('library', null)).toBe(true)
  })
})

describe('uses', () => {
  it('counts the policies using a library type', () => {
    expect(usesLabel([])).toBe('Not on any policy yet')
    expect(usesLabel([use()])).toBe('On 1 policy')
    expect(usesLabel([use(), use({ policy_id: 'p2' })])).toBe('On 2 policies')
  })

  it('shows each policy with its quota, marking its own and switched-off ones', () => {
    expect(useLabel(use())).toBe('UK – London · 4 days')
    expect(useLabel(use({ own_quota: true, annual_quota_days: null }))).toBe('UK – London · Unlimited (own)')
    expect(useLabel(use({ is_active: false }))).toBe('UK – London · off')
  })
})

describe('libraryChoices', () => {
  it('marks types already on the policy and the policy’s own type that could follow instead', () => {
    const sick = entry('e1', 'Sick', 'SL')
    const earned = entry('e2', 'Earned leave', 'EL')
    const casual = entry('e3', 'Casual', 'CL')
    const types = [policyType('Sick', 'SL', 'e1'), policyType('earned  Leave', 'EARN')]
    const [s, e, c] = libraryChoices([sick, earned, casual], types)
    expect([s.onPolicy, s.ownMatch]).toEqual([true, null])
    expect([e.onPolicy, e.ownMatch?.code]).toEqual([false, 'EARN'])
    expect([c.onPolicy, c.ownMatch]).toEqual([false, null])
  })
})

describe('entry drafts', () => {
  it('round-trips a library type through the leave type dialog', () => {
    const sick = { ...entry('e1', 'Sick', 'SL'), uses: [use()] }
    const draft = entryDraft(sick)
    expect(draft.is_active).toBe(true)
    const { is_active: _active, ...rules } = blankType()
    expect(entryBody(draft)).toStrictEqual({ ...rules, name: 'Sick', code: 'SL', annual_quota_days: '4.0' })
  })
})
