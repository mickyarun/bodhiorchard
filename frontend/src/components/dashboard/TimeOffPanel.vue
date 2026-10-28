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

<!-- Time off coming up: who is out in the next three weeks. Shows dates and
     whether the leave is approved, never the leave type. -->
<template>
  <AppPanel title="Time off coming up">
    <template #action><router-link to="/leave/team">Calendar</router-link></template>
    <p v-if="error" class="time-off__empty">{{ error }}</p>
    <ul v-else-if="entries.length" class="time-off">
      <li v-for="entry in entries" :key="entry.request_id" class="time-off__row">
        <AppMonogram :name="entry.user.name" :size="30" />
        <span class="time-off__text">
          <span class="time-off__name">{{ entry.user.name }}</span>
          <span class="time-off__dates">{{ formatDayRange(entry.start_date, entry.end_date) }}</span>
        </span>
        <LeaveStatusChip :status="entry.status" />
      </li>
    </ul>
    <p v-else class="time-off__empty">Nobody is off in the next three weeks.</p>
  </AppPanel>
</template>

<script setup lang="ts">
import AppMonogram from '@/components/common/AppMonogram.vue'
import AppPanel from '@/components/common/AppPanel.vue'
import LeaveStatusChip from '@/components/leave/LeaveStatusChip.vue'
import type { CalendarEntry } from '@/types/leave'
import { formatDayRange } from '@/utils/leaveDates'

defineProps<{ entries: CalendarEntry[]; error: string }>()
</script>

<style scoped>
.time-off {
  list-style: none;
  margin: 0;
  padding: 0;
}
.time-off__row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
}
.time-off__text {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  min-width: 0;
}
.time-off__name {
  font-size: var(--text-sm);
  font-weight: 500;
}
.time-off__dates,
.time-off__empty {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.time-off__empty {
  margin: 0;
  font-size: var(--text-sm);
}
</style>
