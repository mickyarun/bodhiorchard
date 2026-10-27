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

<!-- Directory filters: search and status go to the API; department and
     office narrow what came back. -->
<template>
  <div class="dir-filters">
    <div class="dir-filters__fields">
      <v-text-field
        v-model="search"
        label="Search"
        placeholder="Name, code or email"
        prepend-inner-icon="mdi-magnify"
        clearable
        class="dir-filters__search"
        v-bind="FIELD"
      />
      <v-select
        v-model="office"
        :items="offices"
        label="Office"
        placeholder="All"
        persistent-placeholder
        clearable
        class="dir-filters__select"
        v-bind="FIELD"
      />
      <v-select
        v-model="status"
        :items="STATUS_ITEMS"
        label="Status"
        placeholder="All"
        persistent-placeholder
        clearable
        class="dir-filters__select"
        v-bind="FIELD"
      />
    </div>
    <DepartmentChips v-if="departments.length > 1" v-model="department" :departments="departments" :total="total" />
  </div>
</template>

<script setup lang="ts">
import DepartmentChips from '@/components/people/directory/DepartmentChips.vue'
import type { EmployeeStatus } from '@/types/employee'
import { selectItems, STATUS_LABELS } from '@/utils/employee'
import type { DepartmentCount } from '@/utils/employeeDirectory'

defineProps<{
  departments: DepartmentCount[]
  offices: { title: string; value: string }[]
  /** Everyone the search and status returned, for the "All" chip. */
  total: number
}>()

const search = defineModel<string | null>('search', { required: true })
const status = defineModel<EmployeeStatus | null>('status', { required: true })
const office = defineModel<string | null>('office', { required: true })
const department = defineModel<string | null>('department', { required: true })

const STATUS_ITEMS = selectItems(STATUS_LABELS)
const FIELD = { density: 'compact', variant: 'outlined', hideDetails: true } as const
</script>

<style scoped>
.dir-filters {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}
.dir-filters__fields {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}
.dir-filters__search {
  flex: 1 1 260px;
  max-width: 340px;
}
.dir-filters__select {
  flex: 0 1 180px;
  min-width: 140px;
}
@media (max-width: 600px) {
  .dir-filters__search {
    max-width: none;
  }
  .dir-filters__select {
    flex: 1 1 140px;
  }
}
</style>
