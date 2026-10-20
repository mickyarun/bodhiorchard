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

<!-- Every request in the range: who, when, what, how many days, decision. -->
<template>
  <AppCallout v-if="report?.truncated" variant="info" class="mb-3">
    Showing the first {{ report.rows.length.toLocaleString() }} requests. Narrow the dates or filters to see the rest.
  </AppCallout>
  <v-data-table :headers="headers" :items="report?.rows ?? []" item-value="request_id" density="comfortable" :items-per-page="50">
    <template #[`item.name`]="{ item }"><ReportPersonCell :row="item" /></template>
    <template #[`item.start_date`]="{ item }">
      <div>{{ formatDayRange(item.start_date, item.end_date) }}</div>
      <div v-if="item.half_day !== 'none'" class="text-caption text-medium-emphasis">
        {{ HALF_DAY_LABELS[item.half_day] }}
      </div>
    </template>
    <template #[`item.kind`]="{ item }">{{ item.leave_type ?? KIND_LABELS[item.kind] }}</template>
    <template #[`item.days`]="{ item }">
      <div>{{ formatDays(toNumber(item.days)) }}</div>
      <div v-if="lopLabel(item.lop_days)" class="text-caption text-warning">{{ lopLabel(item.lop_days) }}</div>
    </template>
    <template #[`item.status`]="{ item }"><LeaveStatusChip :status="item.status" /></template>
    <template #[`item.decided_by`]="{ item }">
      {{ item.approval_mode === 'auto_policy' ? 'Automatic' : (item.decided_by ?? '–') }}
    </template>
    <template #no-data><div class="pa-4 text-medium-emphasis">No requests in this range.</div></template>
  </v-data-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveStatusChip from '@/components/leave/LeaveStatusChip.vue'
import ReportPersonCell from '@/components/leave/reports/ReportPersonCell.vue'
import type { RegisterReport } from '@/types/leaveReports'
import { formatDays, HALF_DAY_LABELS, KIND_LABELS, lopLabel, toNumber } from '@/utils/leave'
import { formatDayRange } from '@/utils/leaveDates'

const props = withDefaults(defineProps<{ report: RegisterReport | null; showEmployee?: boolean }>(), {
  showEmployee: true,
})

const HEADERS = [
  { title: 'Employee', key: 'name', sortable: true },
  { title: 'Dates', key: 'start_date', sortable: true },
  { title: 'Type', key: 'kind', sortable: true },
  { title: 'Days', key: 'days', align: 'end', sortable: true },
  { title: 'Status', key: 'status', sortable: true },
  { title: 'Decided by', key: 'decided_by' },
] as const
// One member's history doesn't need their name on every row.
const headers = computed(() => (props.showEmployee ? HEADERS : HEADERS.filter(h => h.key !== 'name')))
</script>
