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
  <p v-if="!days.length" class="agenda__empty">Nobody is out this month.</p>
  <ul v-else class="agenda">
    <li v-for="day in days" :key="day.iso">
      <button
        type="button"
        class="agenda__day"
        :class="{ 'agenda__day--today': day.iso === today }"
        @click="emit('select', day.iso)"
      >
        <span class="agenda__date">{{ formatDayRange(day.iso, day.iso) }}</span>
        <span v-if="day.holiday" class="agenda__holiday">{{ day.holiday }}</span>
        <span class="agenda__entries">
          <CalendarEntryChip v-for="entry in day.entries" :key="entry.request_id" :entry="entry" />
        </span>
      </button>
    </li>
  </ul>
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
.agenda {
  list-style: none;
  margin: 0;
  padding: 0;
}
.agenda li + li {
  border-top: 1px solid var(--color-rule-2);
}
.agenda__day {
  appearance: none;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  width: 100%;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
}
.agenda__day:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.agenda__day:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: -2px;
}
.agenda__day--today {
  box-shadow: inset 3px 0 0 rgb(var(--v-theme-primary));
}
.agenda__date {
  font-size: var(--text-sm);
  font-weight: 600;
}
.agenda__holiday {
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-info));
}
.agenda__entries {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-width: 0;
}
.agenda__empty {
  margin: 0;
  padding: 20px 16px;
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
