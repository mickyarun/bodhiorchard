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

/** Pure helpers for choosing who follows which leave policy. */
import type { EmployeeLeavePolicy } from '@/types/employee'
import type { PolicyMemberRead, PolicyRead } from '@/types/leavePolicy'
import { formatDateOnly } from '@/utils/employee'

/** Filter values: every policy, only the unassigned, or one policy's id. */
export const ALL_POLICIES = 'all'
export const UNASSIGNED = 'unassigned'
export type MemberFilter = string

export const MOVE_POLICY_BODY =
  'They follow it from today. Anyone who has used leave elsewhere this year is prorated from ' +
  'today; everyone else keeps their joining date.'

export const OWN_POLICY_HINT = 'Ask another admin to change your own leave policy.'
export const IMPLICIT_POLICY_HINT = 'Not assigned. Follows the default policy.'

/** Rows per request; a full page means there may be more (search to narrow). */
export const MEMBER_PAGE_SIZE = 500

export interface MemberQuery {
  policy_id?: string
  unassigned?: boolean
  q?: string
  limit: number
}

/** Options for the policy filter, in the policy list's order. */
export function memberFilterItems(policies: readonly PolicyRead[]): { title: string; value: string }[] {
  return [
    { title: 'All policies', value: ALL_POLICIES },
    { title: 'Not assigned (default)', value: UNASSIGNED },
    ...policies.map(p => ({ title: p.name, value: p.id })),
  ]
}

/** What to ask the API for: a policy's followers, only the unassigned, or
 *  everyone, optionally narrowed by a name or email search. */
export function memberQuery(filter: MemberFilter, q: string, limit = MEMBER_PAGE_SIZE): MemberQuery {
  const query: MemberQuery = { limit }
  const term = q.trim()
  if (term) query.q = term
  if (filter === UNASSIGNED) query.unassigned = true
  else if (filter !== ALL_POLICIES) query.policy_id = filter
  return query
}

/** True when the API returned a full page, so some people may be missing. */
export function isTruncated(rows: readonly unknown[], query: MemberQuery): boolean {
  return rows.length >= query.limit
}

/** "On policy since": the transfer date, or their joining date. */
export function policySinceLabel(row: Pick<PolicyMemberRead, 'assigned_on'>): string {
  return row.assigned_on ? formatDateOnly(row.assigned_on) : 'Joining date'
}

/** Nobody but the owner changes their own policy (the API enforces it too). */
export function canChangeMemberPolicy(
  userId: string,
  viewerId: string | null | undefined,
  viewerIsOwner: boolean,
): boolean {
  return viewerIsOwner || userId !== viewerId
}

/** "Move 3 people to UK Office?" */
export function moveTitle(count: number, policyName: string): string {
  return `Move ${count} ${count === 1 ? 'person' : 'people'} to ${policyName}?`
}

/** "India (default)" or "UK Office". */
export function employeePolicyLabel(policy: EmployeeLeavePolicy | null): string | null {
  if (!policy) return null
  return policy.is_default ? `${policy.name} (default)` : policy.name
}
