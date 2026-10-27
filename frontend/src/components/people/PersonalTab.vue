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

<!-- Personal tab: contact, emergency contact, about and celebrations as
     cards. HR edits every field; an employee edits their own contact and
     emergency details. -->
<template>
  <section class="personal">
    <AppCallout
      v-if="!editing && mode === 'self' && !personal.emergency_contact_name"
      variant="info"
      eyebrow="Missing"
    >
      Add an emergency contact so HR can reach someone if needed.
      <template #actions>
        <v-btn size="small" variant="outlined" @click="editing = true">Add now</v-btn>
      </template>
    </AppCallout>

    <PersonalEditForm
      v-if="editing && mode !== 'view'"
      :employee-id="employeeId"
      :personal="personal"
      :mode="mode"
      @close="editing = false"
    />
    <ProfileCards v-else>
      <ProfileFieldCard title="Contact" :fields="contactFields" :editable="canEdit" @edit="editing = true" />
      <ProfileFieldCard
        title="Emergency contact"
        :fields="emergencyFields"
        :editable="canEdit"
        @edit="editing = true"
      />
      <ProfileFieldCard
        title="About"
        :fields="aboutFields"
        :editable="mode === 'hr'"
        @edit="editing = true"
      />
      <CelebrationsCard :employee-id="employeeId" :personal="personal" :mode="mode" :is-self="isSelf" />
    </ProfileCards>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import CelebrationsCard from '@/components/people/CelebrationsCard.vue'
import type { GridField } from '@/components/people/FieldGrid.vue'
import PersonalEditForm from '@/components/people/PersonalEditForm.vue'
import ProfileCards from '@/components/people/profile/ProfileCards.vue'
import ProfileFieldCard from '@/components/people/profile/ProfileFieldCard.vue'
import type { EmployeePersonalRead } from '@/types/employee'
import { BLOOD_GROUP_LABELS, formatDateOnly, GENDER_LABELS } from '@/utils/employee'

const props = defineProps<{
  employeeId: string
  personal: EmployeePersonalRead
  /** hr: every field; self: contact + emergency only; view: read-only. */
  mode: 'hr' | 'self' | 'view'
  /** The viewer is looking at their own record (HR included). */
  isSelf: boolean
}>()

const editing = ref(false)
const canEdit = computed(() => props.mode !== 'view')

/** A field as shown, with "Add" beside it when it's empty and editable. */
function field(label: string, value: string | null, editable: boolean, locked = false): GridField {
  const add = editable && !value
  return {
    label,
    value,
    locked,
    action: add
      ? { label: 'Add', ariaLabel: `Add ${label.toLowerCase()}`, run: () => (editing.value = true) }
      : undefined,
  }
}

const contactFields = computed<GridField[]>(() => [
  field('Phone', props.personal.phone, canEdit.value),
  field('Personal email', props.personal.personal_email, canEdit.value),
])
const emergencyFields = computed<GridField[]>(() => [
  field('Name', props.personal.emergency_contact_name, canEdit.value),
  field('Relation', props.personal.emergency_contact_relation, canEdit.value),
  field('Phone', props.personal.emergency_contact_phone, canEdit.value),
])
// Only HR changes these; the employee sees them with a lock.
const aboutFields = computed<GridField[]>(() => {
  const hr = props.mode === 'hr'
  const locked = props.mode === 'self'
  const { date_of_birth, gender, blood_group } = props.personal
  return [
    field('Date of birth', date_of_birth ? formatDateOnly(date_of_birth) : null, hr, locked),
    field('Gender', gender ? GENDER_LABELS[gender] : null, hr, locked),
    field('Blood group', blood_group ? BLOOD_GROUP_LABELS[blood_group] : null, hr, locked),
  ]
})
</script>

<style scoped>
.personal {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
</style>
