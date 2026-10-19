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
 * An editable copy of one policy for a settings tab. Each tab edits the
 * fields it owns and saves the whole policy (the API takes a full PUT).
 */
import { type Ref, ref, watch } from 'vue'

import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { PolicyRead, PolicyWrite } from '@/types/leavePolicy'
import { policyToWrite } from '@/utils/leavePolicy'

export function usePolicyDraft(policy: Ref<PolicyRead>) {
  const store = useLeavePoliciesStore()
  const draft = ref<PolicyWrite>(policyToWrite(policy.value))
  const saving = ref(false)
  const error = ref('')
  const saved = ref(false)

  watch(policy, next => {
    draft.value = policyToWrite(next)
  })

  async function save(): Promise<void> {
    saving.value = true
    saved.value = false
    error.value = (await store.updatePolicy(policy.value.id, draft.value)) ?? ''
    saving.value = false
    saved.value = !error.value
  }

  return { draft, saving, error, saved, save }
}
