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
  <div class="grid" role="grid">
    <div v-for="label in WEEKDAY_SHORT" :key="label" class="grid__head" role="columnheader">
      {{ label }}
    </div>
    <template v-for="week in weeks" :key="week[0].iso">
      <button
        v-for="day in week"
        :key="day.iso"
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
    </template>
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
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.grid__head {
  padding: 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: var(--tracking-label, 0.08em);
  color: rgb(var(--v-theme-muted));
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.grid__cell {
  appearance: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  min-height: 104px;
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
  border: none;
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
.grid__cell:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.grid__cell:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.grid__cell--outside {
  opacity: 0.45;
}
.grid__cell--holiday {
  background: rgba(var(--v-theme-secondary), 0.08);
}
.grid__cell--today .grid__day {
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
.grid__day {
  font-size: 12px;
  font-weight: 600;
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
}
.grid__holiday {
  font-size: 11px;
  color: rgb(var(--v-theme-secondary));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.grid__entries {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  min-width: 0;
  width: 100%;
}
.grid__more {
  font-size: 11px;
  color: rgb(var(--v-theme-muted));
}
</style>
