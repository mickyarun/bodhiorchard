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
  <AppPage title="Employees" :subtitle="subtitle">
    <template #actions>
      <v-btn
        v-if="canImportSlackPhotos"
        variant="text"
        prepend-icon="mdi-account-box-outline"
        :loading="photos.importing.value"
        @click="importPhotos"
      >
        Import photos from Slack
      </v-btn>
      <v-btn v-if="canInviteMembers" variant="outlined" prepend-icon="mdi-account-plus-outline" @click="inviting = true">
        Invite new hire
      </v-btn>
      <v-btn v-if="canManageEmployees" color="primary" variant="flat" prepend-icon="mdi-plus" @click="addEmployee(null)">
        Add employee
      </v-btn>
    </template>

    <DirectoryFilters
      v-model:search="search"
      v-model:status="status"
      v-model:office="office"
      v-model:department="department"
      :departments="departments"
      :offices="offices"
      :total="officeRows.length"
    />

    <AppCallout v-if="store.error" variant="error">{{ store.error }}</AppCallout>
    <AppCallout v-if="photos.outcome.value" :variant="photos.outcome.value.variant">
      {{ photos.outcome.value.text }}
    </AppCallout>

    <DirectoryTable
      :rows="rows"
      :total="store.directory.length"
      :loading="store.loading"
      :failed="!!store.error"
      :empty-label="emptyLabel"
    />

    <AddEmployeeDialog v-model="adding" :preselect-user-id="preselect" />
    <InviteNewHireDialog v-model="inviting" @invited="invited" />
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import AddEmployeeDialog from '@/components/people/AddEmployeeDialog.vue'
import DirectoryFilters from '@/components/people/directory/DirectoryFilters.vue'
import DirectoryTable from '@/components/people/directory/DirectoryTable.vue'
import InviteNewHireDialog from '@/components/people/InviteNewHireDialog.vue'
import { useDebounced } from '@/composables/useDebounced'
import { usePermissions } from '@/composables/usePermissions'
import { useSlackPhotoImport } from '@/composables/useSlackPhotoImport'
import { useEmployeesStore } from '@/stores/employees'
import type { EmployeeStatus } from '@/types/employee'
import { STATUS_LABELS } from '@/utils/employee'
import {
  departmentCounts,
  directorySummary,
  filterDirectory,
  officeOptions,
} from '@/utils/employeeDirectory'

const store = useEmployeesStore()
const { canManageEmployees, canInviteMembers, canImportSlackPhotos } = usePermissions()
const inviting = ref(false)
const adding = ref(false)
const preselect = ref<string | null>(null)

function addEmployee(userId: string | null): void {
  preselect.value = userId
  adding.value = true
}

/** A new hire's account exists: go straight on to their employee record. */
function invited(userId: string): void {
  if (canManageEmployees.value) addEmployee(userId)
}

// Search and status go to the API; department and office filter the result.
const search = ref<string | null>('')
const status = ref<EmployeeStatus | null>('active')
const department = ref<string | null>(null)
const office = ref<string | null>(null)

// Each filter's choices and counts follow the other filter, so a chip's
// count is what clicking it would show.
const officeRows = computed(() =>
  filterDirectory(store.directory, { department: null, office: office.value }),
)
const departments = computed(() => departmentCounts(officeRows.value))
const offices = computed(() =>
  officeOptions(filterDirectory(store.directory, { department: department.value, office: null })),
)
const rows = computed(() =>
  filterDirectory(officeRows.value, { department: department.value, office: null }),
)

// A new search can leave a picked department or office with nobody in it;
// drop the pick rather than show an empty list for a filter you can't see.
watch(departments, list => {
  if (department.value && !list.some(d => d.name === department.value)) department.value = null
})
watch(offices, list => {
  if (office.value && !list.some(o => o.value === office.value)) office.value = null
})

const subtitle = computed(() =>
  store.loading && !store.directory.length ? '' : directorySummary(store.directory),
)

// The status filter defaults to "Active", so only a search or a narrowing
// filter counts as the user's own for the first-run message.
const emptyLabel = computed(() => {
  if (search.value) return `No one matches "${search.value}".`
  if (department.value || office.value) return 'No one matches these filters.'
  if (status.value && status.value !== 'active') {
    return `No ${STATUS_LABELS[status.value].toLowerCase()} employees.`
  }
  return 'No employee records yet. Add your first employee to get started.'
})

const debouncedSearch = useDebounced(search)
function load(): void {
  void store.fetchDirectory({ q: debouncedSearch.value ?? '', status: status.value })
}

const photos = useSlackPhotoImport()
async function importPhotos(): Promise<void> {
  if (await photos.run()) load()
}
watch([debouncedSearch, status], load)
onMounted(load)
</script>
