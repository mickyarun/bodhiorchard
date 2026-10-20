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

<!-- Employee-wise leave taken in the range, one column per leave type. -->
<template>
  <v-data-table :headers="headers" :items="report?.rows ?? []" item-value="user_id" density="comfortable" :items-per-page="50">
    <template #[`item.name`]="{ item }"><ReportPersonCell :row="item" /></template>
    <template v-for="t in report?.leave_types ?? []" :key="t.id" #[`item.type_${t.id}`]="{ item }">
      {{ days(item.leave_by_type[t.id]) }}
    </template>
    <template #[`item.leave_days`]="{ item }">{{ days(item.leave_days) }}</template>
    <template #[`item.lop_days`]="{ item }">
      <span :class="{ 'text-warning': toNumber(item.lop_days) > 0 }">{{ days(item.lop_days) }}</span>
    </template>
    <template #[`item.wfh_days`]="{ item }">{{ days(item.wfh_days) }}</template>
    <template #[`item.optional_holidays`]="{ item }">{{ days(item.optional_holidays) }}</template>
    <template #[`item.pending_days`]="{ item }">{{ days(item.pending_days) }}</template>
    <template #no-data><div class="pa-4 text-medium-emphasis">Nobody to show for these filters.</div></template>
  </v-data-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ReportPersonCell from '@/components/leave/reports/ReportPersonCell.vue'
import type { Decimalish } from '@/types/leave'
import type { SummaryReport } from '@/types/leaveReports'
import { formatDays, toNumber } from '@/utils/leave'

const props = defineProps<{ report: SummaryReport | null }>()

const NUMBER = { align: 'end', sortable: true } as const
const headers = computed(() => [
  { title: 'Employee', key: 'name', sortable: true },
  { title: 'Office', key: 'office' },
  ...(props.report?.leave_types ?? []).map(t => ({
    title: t.name,
    key: `type_${t.id}`,
    value: (row: { leave_by_type: Record<string, Decimalish> }) => toNumber(row.leave_by_type[t.id]),
    ...NUMBER,
  })),
  { title: 'Leave days', key: 'leave_days', value: (r: { leave_days: Decimalish }) => toNumber(r.leave_days), ...NUMBER },
  { title: 'Loss of pay', key: 'lop_days', value: (r: { lop_days: Decimalish }) => toNumber(r.lop_days), ...NUMBER },
  { title: 'WFH', key: 'wfh_days', value: (r: { wfh_days: Decimalish }) => toNumber(r.wfh_days), ...NUMBER },
  { title: 'Optional', key: 'optional_holidays', ...NUMBER },
  { title: 'Pending', key: 'pending_days', value: (r: { pending_days: Decimalish }) => toNumber(r.pending_days), ...NUMBER },
])

function days(value: Decimalish | undefined): string {
  const n = toNumber(value)
  return n ? formatDays(n) : '–'
}
</script>
