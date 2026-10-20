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

/** One member's leave history for a leave year, with CSV export. */
import { ref } from 'vue'

import api from '@/services/api'
import type { LeaveKind } from '@/types/leave'
import type { RegisterReport } from '@/types/leaveReports'
import { filenameFrom, saveBlob } from '@/utils/download'
import { extractApiError, extractBlobApiError } from '@/utils/errors'

export function useMemberHistory(userId: () => string) {
  const data = ref<RegisterReport | null>(null)
  const loading = ref(false)
  const error = ref('')
  let call = 0

  function params(year: number | null, kind: LeaveKind | null): Record<string, string | number> {
    const out: Record<string, string | number> = {}
    if (year) out.year = year
    if (kind) out.kind = kind
    return out
  }

  async function load(year: number | null, kind: LeaveKind | null): Promise<void> {
    const current = ++call
    loading.value = true
    error.value = ''
    try {
      const response = await api.get<RegisterReport>(`/v1/leave/history/${userId()}`, {
        params: params(year, kind),
      })
      if (current === call) data.value = response.data
    } catch (err) {
      if (current === call) error.value = extractApiError(err, "Couldn't load leave history.")
    } finally {
      if (current === call) loading.value = false
    }
  }

  async function exportCsv(year: number | null, kind: LeaveKind | null): Promise<string | null> {
    try {
      const response = await api.get<Blob>(`/v1/leave/history/${userId()}/export`, {
        params: params(year, kind),
        responseType: 'blob',
      })
      const disposition = response.headers['content-disposition'] as string | undefined
      saveBlob(response.data, filenameFrom(disposition, 'leave-history.csv'))
      return null
    } catch (err) {
      return await extractBlobApiError(err, "Couldn't export leave history.")
    }
  }

  return { data, loading, error, load, exportCsv }
}
