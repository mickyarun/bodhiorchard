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

<!-- Approvals queue filters: dates (overlapping the leave), kind, type and
     person. On Decided, a date range reaches decisions older than 90 days. -->
<template>
  <div class="d-flex flex-wrap align-center ga-3">
    <DateRangeFilter
      :preset="preset"
      :start="store.filters.start"
      :end="store.filters.end"
      :presets="PRESETS"
      @update:preset="(p: DatePreset) => (preset = p)"
      @update:start="(v: string) => (store.filters.start = v)"
      @update:end="(v: string) => (store.filters.end = v)"
    />
    <v-select v-model="store.filters.kind" :items="KIND_OPTIONS" label="Kind" v-bind="FIELD" />
    <v-select
      v-model="store.filters.leave_type_id"
      :items="store.leaveTypes"
      item-title="name"
      item-value="id"
      label="Leave type"
      v-bind="FIELD"
    />
    <v-autocomplete
      v-model="store.filters.user_id"
      :items="store.people"
      item-title="name"
      item-value="user_id"
      label="Person"
      v-bind="FIELD"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import DateRangeFilter, { type DatePreset } from '@/components/leave/DateRangeFilter.vue'
import { useLeaveApprovalsStore } from '@/stores/leaveApprovals'
import { KIND_OPTIONS } from '@/utils/leaveFilterOptions'

const FIELD = {
  density: 'compact',
  variant: 'outlined',
  hideDetails: true,
  clearable: true,
  class: 'field',
} as const
const PRESETS: DatePreset[] = ['any', 'this_week', 'this_month', 'next_30_days', 'last_month', 'custom']

const store = useLeaveApprovalsStore()
const preset = ref<DatePreset>(store.filters.start ? 'custom' : 'any')
</script>

<style scoped>
.field {
  min-width: 160px;
  max-width: 220px;
}
</style>
