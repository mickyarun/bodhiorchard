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
 * Rows of employees and their leave policy for one table or picker.
 * Reloads when the query changes and after any move; a slow response for
 * an older query is dropped.
 */
import { type Ref, ref, watch } from 'vue'

import { useLeaveAssignmentsStore } from '@/stores/leaveAssignments'
import type { PolicyMemberRead } from '@/types/leavePolicy'
import type { MemberQuery } from '@/utils/policyMembers'

export function usePolicyMembers(query: Ref<MemberQuery>, enabled: Ref<boolean> = ref(true)) {
  const store = useLeaveAssignmentsStore()
  const rows = ref<PolicyMemberRead[]>([])
  const loading = ref(false)
  const error = ref('')
  let latest = 0

  async function load(): Promise<void> {
    const request = ++latest
    loading.value = true
    const result = await store.fetchMembers(query.value)
    if (request !== latest) return
    loading.value = false
    if (typeof result === 'string') {
      error.value = result
      rows.value = []
      return
    }
    error.value = ''
    rows.value = result
  }

  // Separate sources so each is compared on its own: an equal query rebuilt
  // as a new object doesn't reload.
  watch(
    [() => JSON.stringify(query.value), () => store.revision, enabled],
    () => {
      if (enabled.value) void load()
    },
    { immediate: true },
  )

  return { rows, loading, error, reload: load }
}
