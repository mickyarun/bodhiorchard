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

<!-- Edit form for the Employment tab's work details (HR only). -->
<template>
  <AppPanel title="Edit employment">
    <v-form @submit.prevent="save">
      <div class="form-grid">
        <v-text-field v-model="draft.employee_code" label="Employee code" v-bind="FIELD" />
        <v-text-field v-model="draft.designation" label="Designation" v-bind="FIELD" />
        <v-text-field v-model="draft.department" label="Department" v-bind="FIELD" />
        <v-select v-model="draft.employment_type" :items="TYPES" label="Employment type" v-bind="FIELD" />
        <v-select v-model="draft.status" :items="STATUSES" label="Status" v-bind="FIELD" />
        <v-text-field v-model="draft.date_of_joining" label="Date of joining" type="date" v-bind="FIELD" />
        <v-text-field
          v-if="draft.status !== 'active'"
          v-model="draft.date_of_exit"
          label="Date of exit"
          type="date"
          v-bind="FIELD"
        />
        <v-text-field v-model="draft.country_code" label="Country (2 letters)" maxlength="2" v-bind="FIELD" />
        <WorkplaceFields v-model:arrangement="draft.work_arrangement" v-model:office-id="draft.office_id" />
      </div>
      <p v-if="draft.status === 'exited' && record.work.status !== 'exited'" class="form-note">
        Marking someone exited also deactivates their account, if your role allows it.
      </p>
      <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
      <div class="d-flex justify-end ga-2 mt-4">
        <v-btn variant="text" @click="emit('close')">Cancel</v-btn>
        <v-btn type="submit" color="primary" variant="flat" :loading="saving">Save changes</v-btn>
      </div>
    </v-form>
  </AppPanel>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPanel from '@/components/common/AppPanel.vue'
import WorkplaceFields from '@/components/people/WorkplaceFields.vue'
import { useEmployeesStore } from '@/stores/employees'
import type { EmployeeRecord, EmployeeWork } from '@/types/employee'
import { blankToNull, EMPLOYMENT_TYPE_LABELS, selectItems, STATUS_LABELS } from '@/utils/employee'

const props = defineProps<{ record: EmployeeRecord }>()
const emit = defineEmits<{ close: [] }>()

const store = useEmployeesStore()
const draft = ref<EmployeeWork>({ ...props.record.work })
const saving = ref(false)
const error = ref('')

const TYPES = selectItems(EMPLOYMENT_TYPE_LABELS)
const STATUSES = selectItems(STATUS_LABELS)
const FIELD = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const

async function save(): Promise<void> {
  saving.value = true
  error.value = (await store.updateWork(props.record.user_id, blankToNull(draft.value))) ?? ''
  saving.value = false
  if (!error.value) emit('close')
}
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.form-note {
  margin: 8px 0 0;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
