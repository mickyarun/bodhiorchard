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

<!-- Month grid, Monday first. Each day lists who's out; holidays tint
     the cell. Clicking a day opens the day drawer. -->
<template>
  <!-- Rows and cells use display: contents, so they give the grid its ARIA
       structure without changing the CSS grid's layout. -->
  <div class="grid" role="grid">
    <div class="grid__row" role="row">
      <div v-for="label in WEEKDAY_SHORT" :key="label" class="grid__head" role="columnheader">
        {{ label }}
      </div>
    </div>
    <div v-for="week in weeks" :key="week[0].iso" class="grid__row" role="row">
      <div v-for="day in week" :key="day.iso" class="grid__slot" role="gridcell">
      <button
        type="button"
        class="grid__cell"
        :class="{
          'grid__cell--outside': !day.inMonth,
          'grid__cell--holiday': !!holidayOn(day.iso, context.holidays),
          'grid__cell--today': day.iso === today,
        }"
        :aria-label="cellLabel(day.iso)"
        @click="emit('select', day.iso)"
      >
        <div class="grid__day">{{ day.day }}</div>
        <div v-if="holidayOn(day.iso, context.holidays)" class="grid__holiday">
          {{ holidayOn(day.iso, context.holidays)?.name }}
        </div>
        <div class="grid__entries">
          <CalendarEntryChip v-for="entry in visible(day.iso)" :key="entry.request_id" :entry="entry" />
          <span v-if="hidden(day.iso)" class="grid__more">+{{ hidden(day.iso) }} more</span>
        </div>
      </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import CalendarEntryChip from '@/components/leave/calendar/CalendarEntryChip.vue'
import type { CalendarEntry } from '@/types/leave'
import { type DayContext, entriesOnDay, holidayOn } from '@/utils/leaveCalendar'
import { formatDayRange, type GridDay, WEEKDAY_SHORT } from '@/utils/leaveDates'

const MAX_CHIPS = 3

const props = defineProps<{
  weeks: GridDay[][]
  entries: CalendarEntry[]
  context: DayContext
  today: string
}>()
const emit = defineEmits<(e: 'select', iso: string) => void>()

function visible(iso: string): CalendarEntry[] {
  return entriesOnDay(props.entries, iso).slice(0, MAX_CHIPS)
}

function hidden(iso: string): number {
  return Math.max(0, entriesOnDay(props.entries, iso).length - MAX_CHIPS)
}

function cellLabel(iso: string): string {
  const count = entriesOnDay(props.entries, iso).length
  const out = count ? `${count} out` : 'nobody out'
  return `${formatDayRange(iso, iso)}, ${out}`
}
</script>

<style scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
}
.grid__row,
.grid__slot {
  display: contents;
}
.grid__head {
  padding: 10px 12px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgb(var(--v-theme-on-surface-variant));
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
.grid__cell {
  appearance: none;
  background: rgb(var(--v-theme-surface));
  color: inherit;
  font: inherit;
  text-align: left;
  min-height: 124px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
  border: none;
  border-right: 1px solid var(--color-rule-2);
  border-bottom: 1px solid var(--color-rule-2);
  min-width: 0;
}
.grid__cell:nth-child(7n) {
  border-right: none;
}
.grid__cell:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.grid__cell:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: -2px;
}
.grid__cell--outside {
  background: rgb(var(--v-theme-background));
}
.grid__cell--outside .grid__day {
  color: rgb(var(--v-theme-on-surface-variant));
}
.grid__cell--holiday {
  background: rgba(var(--v-theme-info), 0.08);
}
.grid__day {
  align-self: flex-start;
  min-width: 24px;
  height: 24px;
  padding: 0 4px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 500;
}
.grid__cell--today .grid__day {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
  font-weight: 600;
}
.grid__holiday {
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-info));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
}
.grid__entries {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  min-width: 0;
  width: 100%;
}
.grid__more {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
