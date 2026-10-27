<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<!-- Who's out on one day. Type and reason show only when the API sent
     them (HR, the requester and their managers). -->
<template>
  <AppSideSheet
    :model-value="!!day"
    :title="shown ? formatDayRange(shown, shown) : ''"
    :width="360"
    @update:model-value="value => !value && emit('close')"
  >
    <AppCallout v-if="holiday" variant="info" class="mb-3">
      {{ holiday.name }}{{ holiday.kind === 'optional' ? ' (optional holiday)' : '' }}
    </AppCallout>
    <p v-if="!list.length" class="text-body-2 text-medium-emphasis">Nobody is out.</p>
    <div v-for="entry in list" :key="entry.request_id" class="person">
      <div class="d-flex align-center ga-2">
        <v-icon :icon="entry.kind === 'wfh' ? 'mdi-home-outline' : 'mdi-calendar-blank-outline'" size="16" aria-hidden="true" />
        <span class="text-body-2 font-weight-medium">{{ entry.user.name }}</span>
        <LeaveStatusChip v-if="entry.status === 'pending'" :status="entry.status" />
      </div>
      <div class="text-caption text-medium-emphasis">
        {{ describe(entry) }}
      </div>
      <div v-if="entry.reason" class="text-caption mt-1">“{{ entry.reason }}”</div>
    </div>
  </AppSideSheet>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppSideSheet from '@/components/common/AppSideSheet.vue'
import LeaveStatusChip from '@/components/leave/LeaveStatusChip.vue'
import type { CalendarEntry } from '@/types/leave'
import { HALF_DAY_LABELS, KIND_LABELS } from '@/utils/leave'
import { type DayContext, entriesOnDay, holidayOn } from '@/utils/leaveCalendar'
import { formatDayRange } from '@/utils/leaveDates'

const props = defineProps<{
  day: string | null
  entries: CalendarEntry[]
  context: DayContext
}>()
const emit = defineEmits<(e: 'close') => void>()

// The last day opened, so the sheet keeps its content while it slides out.
const shown = ref<string | null>(props.day)
watch(
  () => props.day,
  day => {
    if (day) shown.value = day
  },
)
const list = computed(() => (shown.value ? entriesOnDay(props.entries, shown.value) : []))
const holiday = computed(() => (shown.value ? holidayOn(shown.value, props.context.holidays) : null))

function describe(entry: CalendarEntry): string {
  const what = entry.kind === 'leave' ? (entry.leave_type?.name ?? 'On leave') : KIND_LABELS[entry.kind]
  const parts = [what, formatDayRange(entry.start_date, entry.end_date)]
  if (entry.half_day !== 'none') parts.push(HALF_DAY_LABELS[entry.half_day])
  return parts.join(' · ')
}
</script>

<style scoped>
.person {
  padding: 10px 0;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
</style>
