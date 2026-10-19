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
 * One member's balances and ledger for the profile Leave tab. Visible to
 * HR, the member's managers and the member; adjusting needs leave:configure.
 */
import { ref } from 'vue'

import api from '@/services/api'
import type { BalanceAdjust, MemberBalances } from '@/types/leavePolicy'
import { extractApiError } from '@/utils/errors'

export function useMemberBalances() {
  const data = ref<MemberBalances | null>(null)
  const loading = ref(false)
  const error = ref('')
  let call = 0

  async function load(userId: string): Promise<void> {
    const current = ++call
    loading.value = true
    error.value = ''
    try {
      const response = await api.get<MemberBalances>(`/v1/leave/balances/${userId}`)
      if (current === call) data.value = response.data
    } catch (err) {
      if (current !== call) return
      data.value = null
      error.value = extractApiError(err, "Couldn't load leave balances. Reload to try again.")
    } finally {
      if (current === call) loading.value = false
    }
  }

  async function adjust(userId: string, body: BalanceAdjust): Promise<string | null> {
    try {
      data.value = (
        await api.post<MemberBalances>(`/v1/leave/balances/${userId}/adjust`, body)
      ).data
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't adjust the balance. Check the days and note, then try again.")
    }
  }

  return { data, loading, error, load, adjust }
}
