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
 * Pure helpers for the Members page: the active/inactive filter, role
 * names for display and the pickers' option lists.
 */
import type { Member, RoleOption } from '@/stores/members'
import { ROLE_LABELS, type UserRoleName } from '@/types'
import { plural } from '@/utils/format'

export type MemberStatusFilter = 'active' | 'inactive' | 'all'

export function filterMembersByStatus(members: Member[], filter: MemberStatusFilter): Member[] {
  if (filter === 'all') return members
  return members.filter(m => m.isActive === (filter === 'active'))
}

export function memberStatusOptions(members: Member[]): { title: string; value: MemberStatusFilter }[] {
  const active = members.filter(m => m.isActive).length
  return [
    { title: `Active (${active})`, value: 'active' },
    { title: `Inactive (${members.length - active})`, value: 'inactive' },
    { title: `Everyone (${members.length})`, value: 'all' },
  ]
}

/**
 * "Developer" for the system role ``developer``; a snake_case system name
 * without a label reads as words ("quiz_master" → "Quiz master"); custom
 * roles keep their name.
 */
export function roleTitle(name: string): string {
  const label = ROLE_LABELS[name as UserRoleName]
  if (label) return label
  if (!/^[a-z]+(_[a-z]+)+$/.test(name)) return name
  const words = name.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function roleItems(roles: RoleOption[]): { title: string; value: string }[] {
  return roles.map(r => ({ title: roleTitle(r.name), value: r.id }))
}

/** System roles a custom role can inherit phase ownership from. */
export function baseRoleItems(roles: RoleOption[]): { title: string; value: string }[] {
  return roleItems(roles.filter(r => r.scopeType === 'SYSTEM'))
}

/** Active members as picker options, optionally leaving one out. */
export function memberPickerItems(members: Member[], excludeId = ''): { title: string; value: string }[] {
  return members
    .filter(m => m.isActive && m.id !== excludeId)
    .map(m => ({ title: `${m.name} (${m.email})`, value: m.id }))
}

export function membersSubtitle(members: Member[]): string {
  const active = members.filter(m => m.isActive).length
  return `${plural(active, 'person', 'people')} with access to this workspace`
}
