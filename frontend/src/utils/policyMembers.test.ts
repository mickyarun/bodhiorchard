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

import type { PolicyRead } from '@/types/leavePolicy'
import { newPolicy } from '@/utils/leavePolicy'
import {
  ALL_POLICIES,
  canChangeMemberPolicy,
  employeePolicyLabel,
  isTruncated,
  memberFilterItems,
  MEMBER_PAGE_SIZE,
  memberQuery,
  moveTitle,
  policySinceLabel,
  UNASSIGNED,
} from '@/utils/policyMembers'

describe('memberQuery', () => {
  it('asks the server for only the unassigned', () => {
    expect(memberQuery(UNASSIGNED, '')).toEqual({ unassigned: true, limit: MEMBER_PAGE_SIZE })
  })

  it('passes a policy id and a trimmed search', () => {
    expect(memberQuery('uk', '  ana ', 20)).toEqual({ policy_id: 'uk', q: 'ana', limit: 20 })
    expect(memberQuery(ALL_POLICIES, '')).toEqual({ limit: MEMBER_PAGE_SIZE })
  })

  it('flags a full page as possibly cut off', () => {
    const query = memberQuery(ALL_POLICIES, '', 2)
    expect(isTruncated([1], query)).toBe(false)
    expect(isTruncated([1, 2], query)).toBe(true)
  })
})

describe('memberFilterItems', () => {
  it('starts with all and not assigned, then each policy', () => {
    const policies: PolicyRead[] = [
      { ...newPolicy(), name: 'India', id: 'p1', is_default: true, employee_count: 3, has_requests: false },
    ]
    expect(memberFilterItems(policies).map(i => i.value)).toEqual([ALL_POLICIES, UNASSIGNED, 'p1'])
  })
})

describe('labels', () => {
  it('shows the transfer date or the joining date', () => {
    expect(policySinceLabel({ assigned_on: null })).toBe('Joining date')
    expect(policySinceLabel({ assigned_on: '2026-03-02' })).toBe('2 Mar 2026')
  })

  it('titles the move', () => {
    expect(moveTitle(3, 'UK Office')).toBe('Move 3 people to UK Office?')
    expect(moveTitle(1, 'UK Office')).toBe('Move 1 person to UK Office?')
  })

  it('marks the default policy on a profile', () => {
    expect(employeePolicyLabel({ id: 'p', name: 'India', is_default: true, explicit: false })).toBe(
      'India (default)',
    )
    expect(employeePolicyLabel({ id: 'p', name: 'UK', is_default: false, explicit: true })).toBe('UK')
    expect(employeePolicyLabel(null)).toBeNull()
  })
})

describe('canChangeMemberPolicy', () => {
  it('stops people changing their own policy unless they own the org', () => {
    expect(canChangeMemberPolicy('me', 'me', false)).toBe(false)
    expect(canChangeMemberPolicy('me', 'me', true)).toBe(true)
    expect(canChangeMemberPolicy('them', 'me', false)).toBe(true)
  })
})
