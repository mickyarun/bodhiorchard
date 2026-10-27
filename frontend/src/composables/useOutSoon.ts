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
 * Who else is out in the next few days, from the team calendar API. The API
 * leaves out the leave type for coworkers, and so does this.
 */
import { onMounted, ref } from 'vue'

import api from '@/services/api'
import type { CalendarRead } from '@/types/leave'
import { extractApiError } from '@/utils/errors'
import { addDays, toIsoDate } from '@/utils/leaveDates'
import { type OutRow, outSoon } from '@/utils/leaveHome'

export function useOutSoon(days: number, limit: number) {
  const rows = ref<OutRow[]>([])
  /** People past the limit. */
  const more = ref(0)
  const loading = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    const start = toIsoDate(new Date())
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<CalendarRead>('/v1/leave/calendar', {
        params: { start, end: addDays(start, days - 1) },
      })
      const result = outSoon(data.entries, start, days, limit)
      rows.value = result.rows
      more.value = result.more
    } catch (err) {
      rows.value = []
      more.value = 0
      error.value = extractApiError(err, "Couldn't load who's out.")
    } finally {
      loading.value = false
    }
  }

  onMounted(load)

  return { rows, more, loading, error }
}
