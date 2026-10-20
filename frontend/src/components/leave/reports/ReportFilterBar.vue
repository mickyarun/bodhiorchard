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

<!-- Filters for the leave reports; each report shows only the ones it uses. -->
<template>
  <div class="d-flex flex-wrap align-center ga-3">
    <DateRangeFilter
      v-if="store.report !== 'balances'"
      :preset="store.preset"
      :start="store.filters.start"
      :end="store.filters.end"
      :presets="PRESETS"
      @update:preset="(p: DatePreset) => store.setPreset(p as RangePreset)"
      @update:start="(v: string) => (store.filters.start = v)"
      @update:end="(v: string) => (store.filters.end = v)"
    />
    <v-select
      v-else
      v-model="store.filters.year"
      :items="years"
      label="Leave year"
      density="compact"
      variant="outlined"
      hide-details
      class="field"
    />
    <v-autocomplete
      v-model="store.filters.user_id"
      :items="scope?.people ?? []"
      item-title="name"
      item-value="user_id"
      label="Person"
      v-bind="FIELD"
    />
    <v-select
      v-if="scope?.departments.length"
      v-model="store.filters.department"
      :items="scope.departments"
      label="Department"
      v-bind="FIELD"
    />
    <v-select
      v-if="(scope?.offices.length ?? 0) > 1"
      v-model="store.filters.office_id"
      :items="scope?.offices"
      item-title="name"
      item-value="id"
      label="Office"
      v-bind="FIELD"
    />
    <v-select
      v-if="(scope?.policies.length ?? 0) > 1"
      v-model="store.filters.policy_id"
      :items="scope?.policies"
      item-title="name"
      item-value="id"
      label="Policy"
      v-bind="FIELD"
    />
    <v-autocomplete
      v-if="scope?.all"
      v-model="store.filters.manager_id"
      :items="scope.people"
      item-title="name"
      item-value="user_id"
      label="Reports to"
      v-bind="FIELD"
    />
    <template v-if="store.report === 'register'">
      <v-select v-model="store.filters.kind" :items="kinds" label="Kind" v-bind="FIELD" />
      <v-select
        v-model="store.filters.leave_type_id"
        :items="scope?.leave_types ?? []"
        item-title="name"
        item-value="id"
        label="Leave type"
        v-bind="FIELD"
      />
      <v-select v-model="store.filters.status" :items="statuses" label="Status" v-bind="FIELD" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DateRangeFilter, { type DatePreset } from '@/components/leave/DateRangeFilter.vue'
import { useLeaveReportsStore } from '@/stores/leaveReports'
import type { LeaveKind, LeaveStatus } from '@/types/leave'
import { KIND_LABELS, STATUS_META } from '@/utils/leave'
import type { RangePreset } from '@/utils/leaveRanges'

const FIELD = {
  density: 'compact',
  variant: 'outlined',
  hideDetails: true,
  clearable: true,
  class: 'field',
} as const
const PRESETS: DatePreset[] = ['this_month', 'last_month', 'this_quarter', 'this_year', 'custom']

const store = useLeaveReportsStore()
const scope = computed(() => store.scope)
const thisYear = new Date().getFullYear()
const years = [
  { title: 'Current leave year', value: null },
  ...[thisYear + 1, thisYear, thisYear - 1, thisYear - 2].map(y => ({ title: String(y), value: y })),
]
const kinds = (Object.keys(KIND_LABELS) as LeaveKind[]).map(value => ({ value, title: KIND_LABELS[value] }))
const statuses = (Object.keys(STATUS_META) as LeaveStatus[]).map(value => ({
  value,
  title: STATUS_META[value].label,
}))
</script>

<style scoped>
.field {
  min-width: 160px;
  max-width: 220px;
}
</style>
