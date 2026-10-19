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

<!-- Personal tab: contact, emergency contact, and about. HR edits every
     field; an employee edits their own contact and emergency details. -->
<template>
  <section>
    <AppCallout
      v-if="!editing && mode === 'self' && !personal.emergency_contact_name"
      variant="info"
      eyebrow="Missing"
      class="mb-4"
    >
      Add an emergency contact so HR can reach someone if needed.
      <template #actions>
        <v-btn size="small" variant="tonal" @click="startEdit">Add now</v-btn>
      </template>
    </AppCallout>

    <div class="d-flex justify-end mb-2">
      <v-btn
        v-if="mode !== 'view' && !editing"
        variant="tonal"
        size="small"
        prepend-icon="mdi-pencil-outline"
        @click="startEdit"
      >
        {{ mode === 'self' ? 'Edit my details' : 'Edit' }}
      </v-btn>
    </div>

    <template v-if="!editing">
      <div class="section-eyebrow">Contact</div>
      <FieldGrid :fields="contactFields" />
      <div class="section-eyebrow mt-6">Emergency contact</div>
      <FieldGrid :fields="emergencyFields" />
      <div class="section-eyebrow mt-6">About</div>
      <FieldGrid :fields="aboutFields" />
    </template>

    <v-form v-else @submit.prevent="save">
      <div class="form-grid">
        <v-text-field v-model="draft.phone" label="Phone" v-bind="field" />
        <v-text-field v-model="draft.personal_email" label="Personal email" type="email" v-bind="field" />
        <v-text-field v-model="draft.emergency_contact_name" label="Emergency contact" v-bind="field" />
        <v-text-field v-model="draft.emergency_contact_relation" label="Relation" v-bind="field" />
        <v-text-field v-model="draft.emergency_contact_phone" label="Emergency phone" v-bind="field" />
        <template v-if="mode === 'hr'">
          <v-text-field v-model="draft.date_of_birth" label="Date of birth" type="date" v-bind="field" />
          <v-select v-model="draft.gender" :items="GENDERS" label="Gender" clearable v-bind="field" />
          <v-select v-model="draft.blood_group" :items="BLOOD_GROUPS" label="Blood group" clearable v-bind="field" />
        </template>
      </div>
      <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
      <div class="d-flex justify-end ga-2 mt-4">
        <v-btn variant="text" @click="editing = false">Cancel</v-btn>
        <v-btn type="submit" color="primary" :loading="saving">Save changes</v-btn>
      </div>
    </v-form>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import FieldGrid, { type GridField } from '@/components/people/FieldGrid.vue'
import { useEmployeesStore } from '@/stores/employees'
import type { EmployeePersonal } from '@/types/employee'
import {
  blankToNull,
  BLOOD_GROUP_LABELS,
  formatDateOnly,
  GENDER_LABELS,
  selectItems,
} from '@/utils/employee'

const props = defineProps<{
  employeeId: string
  personal: EmployeePersonal
  /** hr: every field; self: contact + emergency only; view: read-only. */
  mode: 'hr' | 'self' | 'view'
}>()

const store = useEmployeesStore()
const editing = ref(false)
const saving = ref(false)
const error = ref('')
const draft = ref<EmployeePersonal>({ ...props.personal })

const GENDERS = selectItems(GENDER_LABELS)
const BLOOD_GROUPS = selectItems(BLOOD_GROUP_LABELS)
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const

const locked = computed(() => props.mode === 'self')
const contactFields = computed<GridField[]>(() => [
  { label: 'Phone', value: props.personal.phone },
  { label: 'Personal email', value: props.personal.personal_email },
])
const emergencyFields = computed<GridField[]>(() => [
  { label: 'Name', value: props.personal.emergency_contact_name },
  { label: 'Relation', value: props.personal.emergency_contact_relation },
  { label: 'Phone', value: props.personal.emergency_contact_phone },
])
const aboutFields = computed<GridField[]>(() => [
  { label: 'Date of birth', value: formatDateOnly(props.personal.date_of_birth), locked: locked.value },
  {
    label: 'Gender',
    value: props.personal.gender ? GENDER_LABELS[props.personal.gender] : null,
    locked: locked.value,
  },
  {
    label: 'Blood group',
    value: props.personal.blood_group ? BLOOD_GROUP_LABELS[props.personal.blood_group] : null,
    locked: locked.value,
  },
])

function startEdit(): void {
  draft.value = { ...props.personal }
  error.value = ''
  editing.value = true
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
  if (!error.value) editing.value = false
}
</script>

<style scoped>
.section-eyebrow {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.7;
  margin-bottom: 8px;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
</style>
