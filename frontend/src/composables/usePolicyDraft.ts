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
 * One editable copy of a policy for a form that owns some of its fields
 * (`fields`). Saving sends the latest policy with only those fields
 * replaced, so it never undoes another form's save; and a refresh of the
 * policy (after any save) only replaces the draft when it has no unsaved
 * edits.
 */
import { computed, type Ref, ref, watch } from 'vue'

import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { PolicyRead, PolicyWrite } from '@/types/leavePolicy'
import {
  mergePolicyFields,
  type PolicyField,
  policyToWrite,
  samePolicyFields,
} from '@/utils/leavePolicy'

export function usePolicyDraft(policy: Ref<PolicyRead>, fields: readonly PolicyField[]) {
  const store = useLeavePoliciesStore()
  const draft = ref<PolicyWrite>(policyToWrite(policy.value))
  const saving = ref(false)
  const error = ref('')

  const dirty = computed(() => !samePolicyFields(draft.value, policyToWrite(policy.value), fields))

  watch(policy, (next, previous) => {
    const untouched = samePolicyFields(draft.value, policyToWrite(previous), fields)
    if (next.id !== previous.id || untouched) {
      draft.value = policyToWrite(next)
      error.value = ''
    }
  })

  function discard(): void {
    draft.value = policyToWrite(policy.value)
    error.value = ''
  }

  /** Resolves to true once saved. */
  async function save(): Promise<boolean> {
    const id = policy.value.id
    saving.value = true
    const body = mergePolicyFields(policyToWrite(policy.value), draft.value, fields)
    error.value = (await store.updatePolicy(id, body)) ?? ''
    saving.value = false
    if (error.value) return false
    // Take the saved values (the server may tidy them), unless more was
    // typed while the request was out: that stays as an unsaved edit.
    const fresh = store.policies.find(p => p.id === id)
    if (fresh && samePolicyFields(draft.value, body, fields)) draft.value = policyToWrite(fresh)
    return true
  }

  return { draft, dirty, saving, error, save, discard }
}
