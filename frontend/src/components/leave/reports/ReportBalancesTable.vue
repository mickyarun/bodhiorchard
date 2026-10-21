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

<!-- Balances per member and leave type for a leave year. "Encashable at exit"
     is what would be paid out if they left today ('—' for other types). -->
<template>
  <v-data-table item-value="key" :headers="HEADERS" :items="rows" density="comfortable" :items-per-page="50">
    <template #[`item.name`]="{ item }"><ReportPersonCell :row="item" /></template>
    <template #[`item.allocated`]="{ item }">{{ limit(item.allocated) }}</template>
    <template #[`item.earned`]="{ item }">{{ limit(item.earned) }}</template>
    <template #[`item.used`]="{ item }">{{ formatDays(toNumber(item.used)) }}</template>
    <template #[`item.pending`]="{ item }">{{ formatDays(toNumber(item.pending)) }}</template>
    <template #[`item.available`]="{ item }">
      <span :class="{ 'text-error': toNumberOrNull(item.available) !== null && toNumber(item.available) < 0 }">
        {{ limit(item.available) }}
      </span>
    </template>
    <template #[`item.encashable`]="{ item }">
      {{ toNumberOrNull(item.encashable) === null ? '—' : formatDays(toNumber(item.encashable)) }}
    </template>
    <template #[`item.lop_days`]="{ item }">
      <span :class="{ 'text-warning': toNumber(item.lop_days) > 0 }">{{ formatDays(toNumber(item.lop_days)) }}</span>
    </template>
    <template #no-data><div class="pa-4 text-medium-emphasis">Nobody to show for these filters.</div></template>
  </v-data-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ReportPersonCell from '@/components/leave/reports/ReportPersonCell.vue'
import type { Decimalish } from '@/types/leave'
import type { BalanceReport } from '@/types/leaveReports'
import { formatDays, toNumber, toNumberOrNull } from '@/utils/leave'

const props = defineProps<{ report: BalanceReport | null }>()
// One row per member per leave type.
const rows = computed(() =>
  (props.report?.rows ?? []).map(r => ({ ...r, key: `${r.user_id}:${r.leave_type_id}` })),
)

const HEADERS = [
  { title: 'Employee', key: 'name', sortable: true },
  { title: 'Year', key: 'leave_year', sortable: true },
  { title: 'Leave type', key: 'leave_type', sortable: true },
  { title: 'Allocated', key: 'allocated', align: 'end' },
  { title: 'Earned so far', key: 'earned', align: 'end' },
  { title: 'Used', key: 'used', align: 'end' },
  { title: 'Pending', key: 'pending', align: 'end' },
  { title: 'Available', key: 'available', align: 'end' },
  { title: 'Encashable at exit', key: 'encashable', align: 'end' },
  { title: 'Loss of pay (year)', key: 'lop_days', align: 'end' },
] as const

function limit(value: Decimalish | null): string {
  const n = toNumberOrNull(value)
  return n === null ? 'No limit' : formatDays(n)
}
</script>
