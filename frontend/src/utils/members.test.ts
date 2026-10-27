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
import type { Member, RoleOption } from '@/stores/members'
import {
  baseRoleItems,
  filterMembersByStatus,
  memberPickerItems,
  membersSubtitle,
  memberStatusOptions,
  roleItems,
  roleTitle,
} from './members'

function member(id: string, isActive: boolean): Member {
  return {
    id,
    email: `${id}@example.com`,
    name: id.toUpperCase(),
    role: 'developer',
    roleId: null,
    roleName: null,
    avatarUrl: null,
    githubUsername: null,
    slackId: null,
    isActive,
    mustChangePassword: false,
    createdAt: '2026-10-01T00:00:00Z',
    emailAliases: [],
  }
}

function role(id: string, name: string, scopeType: string): RoleOption {
  return { id, name, description: null, scopeType, baseRoleId: null, baseRoleName: null, permissions: [] }
}

const members = [member('a', true), member('b', false), member('c', true)]

describe('status filter', () => {
  it('keeps the chosen group', () => {
    expect(filterMembersByStatus(members, 'active').map(m => m.id)).toEqual(['a', 'c'])
    expect(filterMembersByStatus(members, 'inactive').map(m => m.id)).toEqual(['b'])
    expect(filterMembersByStatus(members, 'all')).toHaveLength(3)
  })
  it('counts each option', () => {
    expect(memberStatusOptions(members).map(o => o.title)).toEqual(['Active (2)', 'Inactive (1)', 'Everyone (3)'])
  })
})

describe('roles', () => {
  const roles = [role('r1', 'developer', 'SYSTEM'), role('r2', 'Senior Architect', 'CUSTOM')]
  it('names system roles for people and keeps custom names', () => {
    expect(roleTitle('org_owner')).toBe('Org Owner')
    expect(roleTitle('Senior Architect')).toBe('Senior Architect')
    expect(roleTitle('quiz_master')).toBe('Quiz master')
    expect(roleTitle('ops')).toBe('ops')
    expect(roleItems(roles)).toEqual([
      { title: 'Developer', value: 'r1' },
      { title: 'Senior Architect', value: 'r2' },
    ])
  })
  it('offers only system roles as a base', () => {
    expect(baseRoleItems(roles)).toEqual([{ title: 'Developer', value: 'r1' }])
  })
})

describe('memberPickerItems', () => {
  it('lists active members except the excluded one', () => {
    expect(memberPickerItems(members, 'a')).toEqual([{ title: 'C (c@example.com)', value: 'c' }])
  })
})

describe('membersSubtitle', () => {
  it('counts people with access', () => {
    expect(membersSubtitle(members)).toBe('2 people with access to this workspace')
  })
})
