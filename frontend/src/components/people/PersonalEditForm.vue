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

<!-- Edit form for the Personal tab. HR edits every field; an employee
     edits their own contact and emergency details only. -->
<template>
  <AppPanel :title="mode === 'self' ? 'Edit my details' : 'Edit personal details'">
    <v-form @submit.prevent="save">
      <div class="form-grid">
        <v-text-field v-model="draft.phone" label="Phone" v-bind="FIELD" />
        <v-text-field v-model="draft.personal_email" label="Personal email" type="email" v-bind="FIELD" />
        <v-text-field v-model="draft.emergency_contact_name" label="Emergency contact" v-bind="FIELD" />
        <v-text-field v-model="draft.emergency_contact_relation" label="Relation" v-bind="FIELD" />
        <v-text-field v-model="draft.emergency_contact_phone" label="Emergency phone" v-bind="FIELD" />
        <template v-if="mode === 'hr'">
          <v-text-field v-model="draft.date_of_birth" label="Date of birth" type="date" v-bind="FIELD" />
          <v-select v-model="draft.gender" :items="GENDERS" label="Gender" clearable v-bind="FIELD" />
          <v-select v-model="draft.blood_group" :items="BLOOD_GROUPS" label="Blood group" clearable v-bind="FIELD" />
        </template>
      </div>
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
import { useEmployeesStore } from '@/stores/employees'
import type { EmployeePersonal, EmployeePersonalRead } from '@/types/employee'
import { blankToNull, BLOOD_GROUP_LABELS, GENDER_LABELS, selectItems } from '@/utils/employee'

const props = defineProps<{
  employeeId: string
  personal: EmployeePersonalRead
  /** hr: every field; self: contact + emergency only. */
  mode: 'hr' | 'self'
}>()

const emit = defineEmits<{ close: [] }>()

const store = useEmployeesStore()
const draft = ref<EmployeePersonal>(personalOnly(props.personal))
const saving = ref(false)
const error = ref('')

const GENDERS = selectItems(GENDER_LABELS)
const BLOOD_GROUPS = selectItems(BLOOD_GROUP_LABELS)
const FIELD = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const

/** The editable personal fields, without the read-only opt-outs. */
function personalOnly(source: EmployeePersonalRead): EmployeePersonal {
  const { celebrate_birthday: _b, celebrate_anniversary: _a, ...rest } = source
  return rest
}

async function save(): Promise<void> {
  saving.value = true
  const values = blankToNull(draft.value)
  error.value =
    (props.mode === 'self'
      ? await store.updateMyContact({
          phone: values.phone,
          personal_email: values.personal_email,
          emergency_contact_name: values.emergency_contact_name,
          emergency_contact_relation: values.emergency_contact_relation,
          emergency_contact_phone: values.emergency_contact_phone,
        })
      : await store.updatePersonal(props.employeeId, values)) ?? ''
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
</style>
