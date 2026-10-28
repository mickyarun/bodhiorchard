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

/**
 * What the UI shows each person. Role flags (owner, admin) come from the
 * role; everything else from the granted permissions only, so a role name
 * never stands in for a permission the API would refuse.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

const auth = vi.hoisted(() => ({ user: null as { role?: string; permissions?: string[] } | null }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => auth }))

import { usePermissions } from '@/composables/usePermissions'

function signIn(role: string, permissions: string[]): void {
  auth.user = reactive({ role, permissions })
}

beforeEach(() => {
  auth.user = null
})

describe('role flags', () => {
  it('treats the org owner as owner and admin', () => {
    signIn('org_owner', [])
    const p = usePermissions()
    expect(p.isOrgOwner.value).toBe(true)
    expect(p.isOrgAdmin.value).toBe(true)
  })

  it('treats a platform admin as admin but not owner', () => {
    signIn('admin', [])
    const p = usePermissions()
    expect(p.isOrgAdmin.value).toBe(true)
    expect(p.isOrgOwner.value).toBe(false)
  })

  it.each(['developer', 'tech_lead', 'hr', ''])('gives %s neither flag', (role) => {
    signIn(role, ['org:edit_settings', 'employees:manage'])
    const p = usePermissions()
    expect(p.isOrgAdmin.value).toBe(false)
    expect(p.isOrgOwner.value).toBe(false)
  })

  it('does not grant permissions from the owner role alone', () => {
    // The API sends the owner every permission; the role is not a shortcut.
    signIn('org_owner', [])
    const p = usePermissions()
    expect(p.canApproveLeave.value).toBe(false)
    expect(p.canCreateBuds.value).toBe(false)
    expect(p.canAccessEngineering.value).toBe(false)
  })
})

describe('signed out', () => {
  it('allows nothing', () => {
    const p = usePermissions()
    expect(p.hasPermission('buds:view')).toBe(false)
    expect(p.hasAnyPermission('buds:view', 'bugs:view')).toBe(false)
    expect(p.isOrgAdmin.value).toBe(false)
    expect(p.canViewBugs.value).toBe(false)
    expect(p.canAccessEngineering.value).toBe(false)
  })

  it('allows nothing for a profile without a permission list', () => {
    auth.user = { role: 'developer' }
    expect(usePermissions().hasPermission('buds:view')).toBe(false)
  })
})

describe('permission gates', () => {
  it('opens the engineering workspace only with its permission', () => {
    signIn('developer', ['workspace:engineering'])
    expect(usePermissions().canAccessEngineering.value).toBe(true)
    signIn('hr', ['employees:manage'])
    expect(usePermissions().canAccessEngineering.value).toBe(false)
  })

  it('lets HR approve and configure leave without engineering access', () => {
    signIn('hr', ['leave:approve', 'leave:configure', 'leave:reports', 'employees:manage'])
    const p = usePermissions()
    expect(p.canApproveLeave.value).toBe(true)
    expect(p.canConfigureLeave.value).toBe(true)
    expect(p.canViewLeaveReports.value).toBe(true)
    expect(p.canViewEmployees.value).toBe(true)
    expect(p.canManageCelebrations.value).toBe(true)
    expect(p.canControlCelebrationChannel.value).toBe(false)
  })

  it('separates viewing code settings from changing repositories', () => {
    signIn('developer', ['integrations:configure'])
    const p = usePermissions()
    expect(p.canViewCodeSettings.value).toBe(true)
    expect(p.canManageRepos.value).toBe(false)
  })

  it('keeps QA off BUD edits while letting them test', () => {
    signIn('qa', ['buds:view', 'buds:test'])
    const p = usePermissions()
    expect(p.canEditBuds.value).toBe(false)
    expect(p.canCreateBuds.value).toBe(false)
  })

  it('follows a permission change on the same user', () => {
    signIn('developer', [])
    const p = usePermissions()
    expect(p.canCreateBuds.value).toBe(false)
    auth.user!.permissions!.push('buds:create')
    expect(p.canCreateBuds.value).toBe(true)
  })
})

describe('bug board fallbacks for older role tokens', () => {
  it('accepts the legacy BUD permissions', () => {
    signIn('developer', ['buds:view', 'buds:edit'])
    const p = usePermissions()
    expect(p.canViewBugs.value).toBe(true)
    expect(p.canReportBugs.value).toBe(true)
    expect(p.canEditBugs.value).toBe(true)
    expect(p.canCommentOnBugs.value).toBe(true)
    // Assigning has no legacy fallback.
    expect(p.canAssignBugs.value).toBe(false)
  })

  it('accepts the new bug permissions on their own', () => {
    signIn('qa', ['bugs:view', 'bugs:report', 'bugs:assign'])
    const p = usePermissions()
    expect(p.canViewBugs.value).toBe(true)
    expect(p.canReportBugs.value).toBe(true)
    expect(p.canAssignBugs.value).toBe(true)
    expect(p.canEditBugs.value).toBe(false)
  })
})
