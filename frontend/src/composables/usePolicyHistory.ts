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

/** A leave policy's configuration history (leave:configure). */
import { ref } from 'vue'

import api from '@/services/api'
import type { ConfigEventRead } from '@/types/leavePolicy'
import { extractApiError } from '@/utils/errors'

export function usePolicyHistory() {
  const events = ref<ConfigEventRead[]>([])
  const loading = ref(false)
  const error = ref('')
  let call = 0

  async function load(policyId: string): Promise<void> {
    const current = ++call
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<ConfigEventRead[]>(`/v1/leave/policies/${policyId}/history`)
      if (current === call) events.value = data
    } catch (err) {
      if (current === call) {
        events.value = []
        error.value = extractApiError(err, "Couldn't load this policy's history. Reload to try again.")
      }
    } finally {
      if (current === call) loading.value = false
    }
  }

  return { events, loading, error, load }
}
