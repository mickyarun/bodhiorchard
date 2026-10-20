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

<!-- Employee directory: members who have an employee record. -->
<template>
  <div class="pa-6 directory">
    <div class="d-flex align-start justify-space-between flex-wrap ga-3 mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold bo-display">Employees</h1>
        <p class="text-body-2 text-medium-emphasis">{{ countLabel }}</p>
      </div>
      <v-btn v-if="canManageEmployees" color="primary" prepend-icon="mdi-plus" @click="adding = true">
        Add employee
      </v-btn>
    </div>

    <div class="d-flex flex-wrap ga-3 mb-4">
      <v-text-field
        v-model="search"
        prepend-inner-icon="mdi-magnify"
        placeholder="Search name, code, email"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        style="max-width: 320px"
      />
      <v-select
        v-model="status"
        :items="STATUS_ITEMS"
        label="Status"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        style="max-width: 180px"
      />
    </div>

    <AppCallout v-if="store.error" variant="error" class="mb-4">{{ store.error }}</AppCallout>

    <v-card color="surface" rounded="lg">
      <v-progress-linear v-if="store.loading" indeterminate color="primary" />
      <v-table density="comfortable" hover>
        <thead>
          <tr>
            <th>Name</th>
            <th>Code</th>
            <th>Designation</th>
            <th>Department</th>
            <th>Works from</th>
            <th>Manager</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in store.directory"
            :key="row.user_id"
            class="directory__row"
            :class="{ 'directory__row--inactive': row.status === 'exited' || !row.is_active }"
            @click="open(row.user_id)"
          >
            <td>
              <!-- A real link, so keyboards and screen readers can open it too. -->
              <router-link
                :to="{ name: 'employee-profile', params: { userId: row.user_id } }"
                class="directory__name font-weight-medium"
                @click.stop
              >
                {{ row.name }}
              </router-link>
              <div class="text-caption text-medium-emphasis">{{ row.email }}</div>
            </td>
            <td class="bo-mono">{{ row.employee_code || '—' }}</td>
            <td>{{ row.designation || '—' }}</td>
            <td>{{ row.department || '—' }}</td>
            <td>{{ workplaceLabel(row.work_arrangement, row.office) || '—' }}</td>
            <td>{{ managerLabel(row) }}</td>
            <td><EmployeeStatusChip :status="row.status" /></td>
          </tr>
          <tr v-if="!store.loading && store.directory.length === 0">
            <td colspan="7" class="text-center text-medium-emphasis pa-8">{{ emptyLabel }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <AddEmployeeDialog v-model="adding" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import AddEmployeeDialog from '@/components/people/AddEmployeeDialog.vue'
import EmployeeStatusChip from '@/components/people/EmployeeStatusChip.vue'
import { useDebounced } from '@/composables/useDebounced'
import { usePermissions } from '@/composables/usePermissions'
import { useEmployeesStore } from '@/stores/employees'
import type { DirectoryEntry, EmployeeStatus } from '@/types/employee'
import { selectItems, STATUS_LABELS, workplaceLabel } from '@/utils/employee'

const store = useEmployeesStore()
const router = useRouter()
const { canManageEmployees } = usePermissions()

const STATUS_ITEMS = selectItems(STATUS_LABELS)
const search = ref('')
const status = ref<EmployeeStatus | null>('active')
const adding = ref(false)

const countLabel = computed(() => {
  const n = store.directory.length
  return `${n} ${n === 1 ? 'person' : 'people'}`
})
// The status filter defaults to "Active", so only a search counts as a
// user filter for the first-run message.
const emptyLabel = computed(() =>
  search.value
    ? `No one matches "${search.value}".`
    : status.value && status.value !== 'active'
      ? `No ${STATUS_LABELS[status.value].toLowerCase()} employees.`
      : 'No employee records yet. Add your first employee to get started.',
)

function managerLabel(row: DirectoryEntry): string {
  if (!row.primary_manager) return '—'
  const extra = row.manager_count > 1 ? ` +${row.manager_count - 1}` : ''
  return `${row.primary_manager.name}${extra}`
}

function open(userId: string): void {
  void router.push({ name: 'employee-profile', params: { userId } })
}

const debouncedSearch = useDebounced(search)
function load(): void {
  void store.fetchDirectory({ q: debouncedSearch.value, status: status.value })
}
watch([debouncedSearch, status], load)
onMounted(load)
</script>

<style scoped>
.directory {
  max-width: 1120px;
}
.directory__name {
  color: inherit;
  text-decoration: none;
  display: block;
}
.directory__name:hover {
  text-decoration: underline;
}
.directory__row {
  cursor: pointer;
}
.directory__row--inactive {
  opacity: 0.55;
}
</style>
