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
import { grantableRoles, roleLabel, temporaryPassword } from '@/utils/inviteNewHire'

function role(name: string, keys: string[]): RoleOption {
  return {
    id: name, name, description: null, scopeType: 'SYSTEM', baseRoleId: null, baseRoleName: null,
    // The API's own shape: resource_id, not resourceId.
    permissions: keys.map(k => ({ resource_id: k }) as unknown as RoleOption['permissions'][number]),
  }
}

const ROLES = [
  role('org_owner', []),
  role('sales', []),
  role('hr', ['leave:approve', 'employees:manage', 'team:invite']),
  role('developer', ['workspace:engineering', 'buds:edit']),
]

describe('grantableRoles', () => {
  it('offers HR only roles within its own permissions, never the owner role', () => {
    const hr = ['leave:approve', 'employees:manage', 'team:invite', 'team:view']
    expect(grantableRoles(ROLES, hr, false).map(r => r.name)).toEqual(['sales', 'hr'])
  })

  it('lets the owner give any role but owner', () => {
    expect(grantableRoles(ROLES, [], true).map(r => r.name)).toEqual(['sales', 'hr', 'developer'])
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
