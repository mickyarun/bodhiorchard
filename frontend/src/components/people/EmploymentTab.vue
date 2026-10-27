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

<!-- Employment tab: work details, leave policy and reporting managers.
     Only HR edits these, and never on their own record. -->
<template>
  <section class="employment">
    <AppCallout v-if="exitNotice" :variant="exitNotice.variant">{{ exitNotice.text }}</AppCallout>
    <AppCallout v-if="policyNotice" :variant="policyNotice.variant">{{ policyNotice.text }}</AppCallout>

    <EmploymentEditForm v-if="editing" :record="record" @close="editing = false" />
    <ProfileCards>
      <template v-if="!editing">
        <ProfileFieldCard title="Role" :fields="roleFields" :editable="record.access.edit_work" @edit="editing = true" />
        <ProfileFieldCard
          title="Dates and place"
          :fields="placeFields"
          :editable="record.access.edit_work"
          @edit="editing = true"
        />
      </template>
      <ManagersEditor
        :employee-id="record.user_id"
        :employee-name="record.name"
        :managers="record.managers"
        :editable="record.access.edit_managers"
      />
      <ProfileFieldCard title="Leave policy" :fields="[leavePolicyField]" />
    </ProfileCards>
    <ChangePolicyDialog v-model="changingPolicy" :record="record" @moved="onPolicyMoved" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import ChangePolicyDialog from '@/components/people/ChangePolicyDialog.vue'
import EmploymentEditForm from '@/components/people/EmploymentEditForm.vue'
import type { GridField } from '@/components/people/FieldGrid.vue'
import ManagersEditor from '@/components/people/ManagersEditor.vue'
import ProfileCards from '@/components/people/profile/ProfileCards.vue'
import ProfileFieldCard from '@/components/people/profile/ProfileFieldCard.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useAuthStore } from '@/stores/auth'
import type { EmployeeRecord } from '@/types/employee'
import type { AssignResult } from '@/types/leavePolicy'
import {
  ARRANGEMENT_LABELS,
  EMPLOYMENT_TYPE_LABELS,
  formatDateOnly,
  STATUS_LABELS,
} from '@/utils/employee'
import { movedSummary, movedVariant } from '@/utils/leavePolicy'
import { canChangeMemberPolicy, employeePolicyLabel } from '@/utils/policyMembers'

const props = defineProps<{ record: EmployeeRecord }>()

const authStore = useAuthStore()
const { canConfigureLeave, isOrgOwner } = usePermissions()
const editing = ref(false)
const changingPolicy = ref(false)
const policyNotice = ref<{ text: string; variant: 'success' | 'warning' } | null>(null)

const locked = computed(() => !props.record.access.edit_work)

const roleFields = computed<GridField[]>(() => {
  const w = props.record.work
  return [
    { label: 'Employee code', value: w.employee_code, locked: locked.value },
    { label: 'Designation', value: w.designation, locked: locked.value },
    { label: 'Department', value: w.department, locked: locked.value },
    { label: 'Employment type', value: EMPLOYMENT_TYPE_LABELS[w.employment_type], locked: locked.value },
    { label: 'Status', value: STATUS_LABELS[w.status], locked: locked.value },
  ]
})

const placeFields = computed<GridField[]>(() => {
  const w = props.record.work
  return [
    { label: 'Date of joining', value: w.date_of_joining ? formatDateOnly(w.date_of_joining) : null, locked: locked.value },
    { label: 'Date of exit', value: w.date_of_exit ? formatDateOnly(w.date_of_exit) : null, locked: locked.value },
    { label: 'Country', value: w.country_code, locked: locked.value },
    { label: 'Work arrangement', value: ARRANGEMENT_LABELS[w.work_arrangement], locked: locked.value },
    { label: 'Office', value: props.record.office?.name ?? null, locked: locked.value },
  ]
})

// Anyone with leave:configure may change it, but never on their own record
// unless they own the org (the assign route checks the same).
const leavePolicyField = computed<GridField>(() => {
  const canChange =
    canConfigureLeave.value &&
    canChangeMemberPolicy(props.record.user_id, authStore.user?.id, isOrgOwner.value)
  return {
    label: 'Policy',
    value: employeePolicyLabel(props.record.leave_policy),
    action: canChange
      ? { label: 'Change', ariaLabel: 'Change leave policy', run: () => (changingPolicy.value = true) }
      : undefined,
  }
})

function onPolicyMoved(result: AssignResult, policyName: string): void {
  policyNotice.value = { text: movedSummary(result, policyName), variant: movedVariant(result) }
}

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
</script>

<style scoped>
.employment {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
</style>
