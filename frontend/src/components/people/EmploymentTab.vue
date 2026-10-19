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

<!-- Employment tab: work details plus reporting managers. Only HR
     edits these, and never on their own record. -->
<template>
  <section>
    <AppCallout v-if="exitNotice" :variant="exitNotice.variant" class="mb-4">
      {{ exitNotice.text }}
    </AppCallout>

    <div class="d-flex justify-end mb-2">
      <v-btn
        v-if="record.access.edit_work && !editing"
        variant="tonal"
        size="small"
        prepend-icon="mdi-pencil-outline"
        @click="startEdit"
      >
        Edit
      </v-btn>
    </div>

    <FieldGrid v-if="!editing" :fields="fields" />

    <v-form v-else @submit.prevent="save">
      <div class="form-grid">
        <v-text-field v-model="draft.employee_code" label="Employee code" v-bind="field" />
        <v-text-field v-model="draft.designation" label="Designation" v-bind="field" />
        <v-text-field v-model="draft.department" label="Department" v-bind="field" />
        <v-select v-model="draft.employment_type" :items="TYPES" label="Employment type" v-bind="field" />
        <v-select v-model="draft.status" :items="STATUSES" label="Status" v-bind="field" />
        <v-text-field v-model="draft.date_of_joining" label="Date of joining" type="date" v-bind="field" />
        <v-text-field
          v-if="draft.status !== 'active'"
          v-model="draft.date_of_exit"
          label="Date of exit"
          type="date"
          v-bind="field"
        />
        <v-text-field v-model="draft.country_code" label="Country (2 letters)" maxlength="2" v-bind="field" />
        <v-text-field v-model="draft.work_location" label="Work location" v-bind="field" />
      </div>
      <p v-if="draft.status === 'exited' && record.work.status !== 'exited'" class="text-caption mt-2">
        Marking someone exited also deactivates their account, if your role allows it.
      </p>
      <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
      <div class="d-flex justify-end ga-2 mt-4">
        <v-btn variant="text" @click="editing = false">Cancel</v-btn>
        <v-btn type="submit" color="primary" :loading="saving">Save changes</v-btn>
      </div>
    </v-form>

    <v-divider class="my-6" />
    <ManagersEditor
      :employee-id="record.user_id"
      :employee-name="record.name"
      :managers="record.managers"
      :editable="record.access.edit_managers"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import FieldGrid, { type GridField } from '@/components/people/FieldGrid.vue'
import ManagersEditor from '@/components/people/ManagersEditor.vue'
import { useEmployeesStore } from '@/stores/employees'
import type { EmployeeRecord, EmployeeWork } from '@/types/employee'
import {
  blankToNull,
  EMPLOYMENT_TYPE_LABELS,
  formatDateOnly,
  selectItems,
  STATUS_LABELS,
} from '@/utils/employee'

const props = defineProps<{ record: EmployeeRecord }>()

const store = useEmployeesStore()
const editing = ref(false)
const saving = ref(false)
const error = ref('')
const draft = ref<EmployeeWork>({ ...props.record.work })

const TYPES = selectItems(EMPLOYMENT_TYPE_LABELS)
const STATUSES = selectItems(STATUS_LABELS)
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const

const fields = computed<GridField[]>(() => {
  const w = props.record.work
  const locked = !props.record.access.edit_work
  return [
    { label: 'Employee code', value: w.employee_code, locked },
    { label: 'Designation', value: w.designation, locked },
    { label: 'Department', value: w.department, locked },
    { label: 'Employment type', value: EMPLOYMENT_TYPE_LABELS[w.employment_type], locked },
    { label: 'Status', value: STATUS_LABELS[w.status], locked },
    { label: 'Date of joining', value: formatDateOnly(w.date_of_joining), locked },
    { label: 'Date of exit', value: w.date_of_exit ? formatDateOnly(w.date_of_exit) : null, locked },
    { label: 'Country', value: w.country_code, locked },
    { label: 'Work location', value: w.work_location, locked },
  ]
})

const exitNotice = computed(() => {
  if (props.record.access_revoked === true) {
    return { variant: 'success' as const, text: `${props.record.name}'s account was deactivated.` }
  }
  if (props.record.access_revoked === false && props.record.is_active) {
    return {
      variant: 'warning' as const,
      text: `${props.record.name} is marked exited but can still sign in. Ask an admin to deactivate their account in Members.`,
    }
  }
  return null
})

function startEdit(): void {
  draft.value = { ...props.record.work }
  error.value = ''
  editing.value = true
}

async function save(): Promise<void> {
  saving.value = true
  error.value = (await store.updateWork(props.record.user_id, blankToNull(draft.value))) ?? ''
  saving.value = false
  if (!error.value) editing.value = false
}
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
</style>
