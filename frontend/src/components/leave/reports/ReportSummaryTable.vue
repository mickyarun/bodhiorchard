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

<!-- Employee-wise leave taken in the range, one column per leave type, each
     with what is left of that type in the leave year the range ends in. -->
<template>
  <p v-if="report?.leave_types.length" class="legend text-caption text-medium-emphasis">
    <strong>Total taken</strong> is all approved leave in these dates. The columns after it
    split that total by leave type, as set up on each person's policy: each shows
    <strong>days taken</strong>, and below it the <strong>days left</strong> in the leave year
    the dates end in (pending requests counted). A dash means the type isn't on that person's
    policy.
  </p>
  <v-data-table :headers="headers" :items="report?.rows ?? []" item-value="user_id" density="comfortable" :items-per-page="50">
    <template #[`item.name`]="{ item }"><ReportPersonCell :row="item" /></template>
    <template v-for="(t, i) in report?.leave_types ?? []" :key="t.key" #[`item.type_${i}`]="{ item }">
      <template v-if="t.key in item.left_by_type">
        <div class="taken" :class="tone(item.leave_by_type[t.key])">{{ formatDays(toNumber(item.leave_by_type[t.key])) }}</div>
        <div class="left text-caption" :class="leftTone(item.left_by_type[t.key])">
          {{ leftLabel(item.left_by_type[t.key]) }}
        </div>
      </template>
      <span v-else :class="tone(item.leave_by_type[t.key])">{{ days(item.leave_by_type[t.key]) }}</span>
    </template>
    <template #[`item.leave_days`]="{ item }">
      <div class="taken" :class="tone(item.leave_days)">{{ days(item.leave_days) }}</div>
      <div
        v-if="item.high_leave"
        class="left text-caption"
        :class="item.high_leave.level === 'warning' ? 'text-warning' : 'text-info'"
        :title="highLeaveForOthers(item.high_leave, item.name)"
      >
        <v-icon icon="mdi-alert-circle-outline" size="12" /> {{ highLeaveShort(item.high_leave) }}
      </div>
    </template>
    <template #[`item.lop_days`]="{ item }">
      <span :class="toNumber(item.lop_days) > 0 ? 'text-warning' : 'zero'">{{ days(item.lop_days) }}</span>
    </template>
    <template #[`item.wfh_days`]="{ item }"><span :class="tone(item.wfh_days)">{{ days(item.wfh_days) }}</span></template>
    <template #[`item.optional_holidays`]="{ item }">
      <span :class="tone(item.optional_holidays)">{{ days(item.optional_holidays) }}</span>
    </template>
    <template #[`item.pending_days`]="{ item }"><span :class="tone(item.pending_days)">{{ days(item.pending_days) }}</span></template>
    <template #[`body.append`]>
      <tr v-if="report?.rows.length" class="totals">
        <th scope="row">Total</th>
        <td v-for="h in headers.slice(1)" :key="h.key" class="text-end">{{ days(totals[h.key]) }}</td>
      </tr>
    </template>
    <template #no-data><div class="pa-4 text-medium-emphasis">Nobody to show for these filters.</div></template>
  </v-data-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ReportPersonCell from '@/components/leave/reports/ReportPersonCell.vue'
import type { Decimalish } from '@/types/leave'
import type { SummaryReport } from '@/types/leaveReports'
import { highLeaveForOthers, highLeaveShort } from '@/utils/highLeave'
import { formatDays, toNumber } from '@/utils/leave'
import { summaryTotals } from '@/utils/leaveReportTotals'

const props = defineProps<{ report: SummaryReport | null }>()

const NUMBER = { align: 'end', sortable: true } as const
const headers = computed(() => [
  { title: 'Employee', key: 'name', sortable: true },
  { title: 'Total taken', key: 'leave_days', value: (r: { leave_days: Decimalish }) => toNumber(r.leave_days), ...NUMBER },
  ...(props.report?.leave_types ?? []).map((t, i) => ({
    title: t.name,
    key: `type_${i}`,
    value: (row: { leave_by_type: Record<string, Decimalish> }) => toNumber(row.leave_by_type[t.key]),
    ...NUMBER,
  })),
  { title: 'Loss of pay', key: 'lop_days', value: (r: { lop_days: Decimalish }) => toNumber(r.lop_days), ...NUMBER },
  { title: 'WFH', key: 'wfh_days', value: (r: { wfh_days: Decimalish }) => toNumber(r.wfh_days), ...NUMBER },
  { title: 'Optional', key: 'optional_holidays', ...NUMBER },
  { title: 'Pending', key: 'pending_days', value: (r: { pending_days: Decimalish }) => toNumber(r.pending_days), ...NUMBER },
])

function leftLabel(value: Decimalish | null | undefined): string {
  return value === null || value === undefined ? 'no limit' : `${formatDays(toNumber(value))} left`
}

function leftTone(value: Decimalish | null | undefined): string {
  if (value === null || value === undefined) return 'text-medium-emphasis'
  return toNumber(value) <= 0 ? 'text-warning' : 'text-medium-emphasis'
}

const totals = computed(() => summaryTotals(props.report))

/** Zero days are a quiet dash. */
function tone(value: Decimalish | undefined): string {
  return toNumber(value) ? '' : 'zero'
}

function days(value: Decimalish | undefined): string {
  const n = toNumber(value)
  return n ? formatDays(n) : '–'
}
</script>

<style scoped>
/* Many type columns: keep headers on one line and let the table scroll. */
:deep(th) {
  white-space: nowrap;
}
.legend {
  padding: 12px 16px 0;
  margin: 0;
}
.taken {
  font-weight: 600;
}
.zero {
  color: rgb(var(--v-theme-on-surface-variant));
  font-weight: 400;
}
.totals th,
.totals td {
  font-weight: 600;
  border-top: 2px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-background));
}
.totals th {
  text-align: left;
  padding: 0 16px;
}
.left {
  white-space: nowrap;
}
</style>
