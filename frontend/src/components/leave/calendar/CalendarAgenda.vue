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

<!-- Narrow-screen team calendar: only the days of the month when
     someone is out or there's a holiday. -->
<template>
  <div v-if="!days.length" class="pa-6 text-body-2 text-medium-emphasis">
    Nobody is out this month.
  </div>
  <v-list v-else bg-color="transparent" density="compact" class="py-0">
    <v-list-item
      v-for="day in days"
      :key="day.iso"
      class="py-2"
      :class="{ 'agenda--today': day.iso === today }"
      @click="emit('select', day.iso)"
    >
      <div class="text-body-2 font-weight-medium">{{ formatDayRange(day.iso, day.iso) }}</div>
      <div v-if="day.holiday" class="text-caption agenda__holiday">{{ day.holiday }}</div>
      <div class="d-flex flex-wrap ga-1 mt-1">
        <CalendarEntryChip v-for="entry in day.entries" :key="entry.request_id" :entry="entry" />
      </div>
    </v-list-item>
  </v-list>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import CalendarEntryChip from '@/components/leave/calendar/CalendarEntryChip.vue'
import type { CalendarEntry } from '@/types/leave'
import { type DayContext, entriesOnDay, holidayOn } from '@/utils/leaveCalendar'
import { formatDayRange, monthDays, type MonthRef } from '@/utils/leaveDates'

const props = defineProps<{
  month: MonthRef
  entries: CalendarEntry[]
  context: DayContext
  today: string
}>()
const emit = defineEmits<(e: 'select', iso: string) => void>()

const days = computed(() =>
  monthDays(props.month)
    .map(iso => ({
      iso,
      holiday: holidayOn(iso, props.context.holidays)?.name ?? '',
      entries: entriesOnDay(props.entries, iso),
    }))
    .filter(day => day.holiday || day.entries.length),
)
</script>

<style scoped>
.agenda__holiday {
  color: rgb(var(--v-theme-secondary));
}
.agenda--today {
  border-left: 3px solid rgb(var(--v-theme-primary));
}
</style>
