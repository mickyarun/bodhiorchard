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
 * Who follows which leave policy, and moving people between policies
 * (leave:configure). Each table keeps its own rows (see
 * usePolicyMembers); `revision` ticks after every move so all of them
 * reload. Actions resolve to their result or a user-facing error.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { AssignResult, PolicyMemberRead } from '@/types/leavePolicy'
import { extractApiError } from '@/utils/errors'
import type { MemberQuery } from '@/utils/policyMembers'

export const useLeaveAssignmentsStore = defineStore('leaveAssignments', () => {
  const revision = ref(0)

  async function fetchMembers(query: MemberQuery): Promise<PolicyMemberRead[] | string> {
    try {
      return (await api.get<PolicyMemberRead[]>('/v1/leave/policy-members', { params: query })).data
    } catch (err) {
      return extractApiError(err, "Couldn't load who follows each policy. Reload to try again.")
    }
  }

  /** Move people onto a policy from today. */
  async function move(policyId: string, userIds: string[]): Promise<AssignResult | string> {
    let result: AssignResult
    try {
      result = (
        await api.post<AssignResult>(`/v1/leave/policies/${policyId}/assign`, {
          user_ids: userIds,
        })
      ).data
    } catch (err) {
      return extractApiError(err, "Couldn't move these people. Try again.")
    }
    revision.value += 1
    // People counts on the policy cards change with every move.
    void useLeavePoliciesStore().fetchPolicies()
    return result
  }

  return { revision, fetchMembers, move }
})
