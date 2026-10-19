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
 * Form state for the leave / WFH / optional-holiday request dialog, with
 * a debounced server preview of what the request would cost and who
 * decides it. The server is the source of truth for both.
 */
import { computed, onScopeDispose, ref, watch } from 'vue'

import { useLeaveStore } from '@/stores/leave'
import type { HalfDay, LeaveKind, LeavePreview, LeaveRequestCreate } from '@/types/leave'
import { toIsoDate } from '@/utils/leaveDates'

const PREVIEW_DELAY_MS = 300

export function useLeaveRequestForm() {
  const store = useLeaveStore()

  const kind = ref<LeaveKind>('leave')
  const leaveTypeId = ref<string | null>(null)
  const holidayId = ref<string | null>(null)
  const startDate = ref('')
  const endDate = ref('')
  const halfDay = ref<HalfDay>('none')
  const reason = ref('')

  const preview = ref<LeavePreview | null>(null)
  const previewError = ref('')
  const previewing = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let call = 0

  const singleDay = computed(() => !!startDate.value && startDate.value === endDate.value)

  const payload = computed<LeaveRequestCreate | null>(() => {
    if (!startDate.value || !endDate.value) return null
    if (kind.value === 'leave' && !leaveTypeId.value) return null
    if (kind.value === 'optional_holiday' && !holidayId.value) return null
    return {
      kind: kind.value,
      leave_type_id: kind.value === 'leave' ? leaveTypeId.value : null,
      holiday_id: kind.value === 'optional_holiday' ? holidayId.value : null,
      start_date: startDate.value,
      end_date: endDate.value,
      half_day: singleDay.value && kind.value !== 'optional_holiday' ? halfDay.value : 'none',
      reason: reason.value.trim() || null,
    }
  })

  const canSend = computed(
    () =>
      !!payload.value &&
      !!preview.value &&
      preview.value.problems.length === 0 &&
      !previewing.value &&
      !previewError.value,
  )

  function reset(preset: LeaveKind): void {
    const today = toIsoDate(new Date())
    kind.value = preset
    leaveTypeId.value = null
    holidayId.value = null
    startDate.value = today
    endDate.value = today
    halfDay.value = 'none'
    reason.value = ''
    // Same key as last time (e.g. reopened with the same kind) won't fire the
    // watcher, so restart the preview here rather than leave a stale result.
    schedulePreview()
  }

  async function runPreview(body: LeaveRequestCreate): Promise<void> {
    const current = ++call
    const result = await store.preview(body)
    if (current !== call) return
    preview.value = result.data
    previewError.value = result.error
    previewing.value = false
  }

  // The reason doesn't change the cost, so it doesn't re-run the preview.
  const previewKey = computed(() =>
    payload.value ? JSON.stringify({ ...payload.value, reason: null }) : '',
  )

  function schedulePreview(): void {
    if (timer) clearTimeout(timer)
    call += 1
    preview.value = null
    previewError.value = ''
    const body = payload.value
    previewing.value = !!body
    if (!body) return
    timer = setTimeout(() => void runPreview(body), PREVIEW_DELAY_MS)
  }

  watch(previewKey, schedulePreview)

  watch(startDate, start => {
    if (start && endDate.value < start) endDate.value = start
  })
  watch(endDate, end => {
    if (end && startDate.value && end < startDate.value) endDate.value = startDate.value
  })
  watch(singleDay, single => {
    if (!single) halfDay.value = 'none'
  })

  onScopeDispose(() => {
    if (timer) clearTimeout(timer)
  })

  return {
    kind,
    leaveTypeId,
    holidayId,
    startDate,
    endDate,
    halfDay,
    reason,
    singleDay,
    payload,
    preview,
    previewError,
    previewing,
    canSend,
    reset,
  }
}
