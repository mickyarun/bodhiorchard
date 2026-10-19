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
 * Team calendar data for one month, keyed by `?month=YYYY-MM`.
 *
 * Fetches the whole visible grid (up to six weeks, inside the API's
 * 93-day limit) so padding days from neighbouring months show too.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import api from '@/services/api'
import type { CalendarRead } from '@/types/leave'
import { extractApiError } from '@/utils/errors'
import type { DayContext } from '@/utils/leaveCalendar'
import {
  buildMonthGrid,
  formatMonthParam,
  monthOf,
  type MonthRef,
  parseMonthParam,
  shiftMonth,
} from '@/utils/leaveDates'

export function useTeamCalendar() {
  const route = useRoute()
  const router = useRouter()

  const data = ref<CalendarRead>({ entries: [], holidays: [] })
  const loading = ref(false)
  const error = ref('')
  let call = 0

  const month = computed<MonthRef>(() => parseMonthParam(route.query.month, monthOf(new Date())))
  const weeks = computed(() => buildMonthGrid(month.value))
  const context = computed<DayContext>(() => ({ holidays: data.value.holidays }))

  async function load(): Promise<void> {
    const current = ++call
    const grid = weeks.value
    const start = grid[0][0].iso
    const end = grid[grid.length - 1][6].iso
    loading.value = true
    error.value = ''
    try {
      const response = await api.get<CalendarRead>('/v1/leave/calendar', { params: { start, end } })
      if (current === call) data.value = response.data
    } catch (err) {
      if (current !== call) return
      data.value = { entries: [], holidays: [] }
      error.value = extractApiError(err, "Couldn't load the team calendar. Reload to try again.")
    } finally {
      if (current === call) loading.value = false
    }
  }

  function goTo(next: MonthRef): void {
    void router.replace({ query: { ...route.query, month: formatMonthParam(next) } })
  }

  function step(delta: number): void {
    goTo(shiftMonth(month.value, delta))
  }

  function today(): void {
    goTo(monthOf(new Date()))
  }

  watch(() => formatMonthParam(month.value), load, { immediate: true })

  return { month, weeks, data, context, loading, error, step, today }
}
