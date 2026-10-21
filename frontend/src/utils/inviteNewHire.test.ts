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

import type { RoleOption } from '@/stores/members'
import { offeredRoles, roleLabel, temporaryPassword } from '@/utils/inviteNewHire'

function role(name: string): RoleOption {
  return { id: name, name, description: null, scopeType: 'SYSTEM', baseRoleId: null, baseRoleName: null, permissions: [] }
}

const ROLES = ['admin', 'sales', 'hr', 'developer'].map(role)

describe('offeredRoles', () => {
  it('offers only what the server says the inviter may give, in list order', () => {
    expect(offeredRoles(ROLES, ['developer', 'sales', 'hr']).map(r => r.name)).toEqual(['sales', 'hr', 'developer'])
    expect(offeredRoles(ROLES, [])).toEqual([])
  })
})

describe('roleLabel', () => {
  it('reads like a word', () => {
    expect(roleLabel('tech_lead')).toBe('Tech lead')
    expect(roleLabel('hr')).toBe('HR')
  })
})

describe('temporaryPassword', () => {
  it('is long enough and skips look-alike characters', () => {
    const password = temporaryPassword()
    expect(password).toHaveLength(12)
    expect(password).not.toMatch(/[0O1lI]/)
    expect(temporaryPassword()).not.toBe(password)
  })
})
