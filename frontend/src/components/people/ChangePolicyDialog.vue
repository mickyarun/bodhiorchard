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

<!-- Change the leave policy one employee follows (leave:configure), from
     their profile. Same rules as moving people in Settings → Leave. -->
<template>
  <v-dialog v-model="open" max-width="520">
    <v-card color="surface" rounded="lg">
      <div class="pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">Change {{ record.name }}'s leave policy</h2>
        <p class="text-body-2 text-medium-emphasis mt-2 mb-5">{{ MOVE_POLICY_BODY }}</p>
        <v-select
          v-model="policyId"
          :items="choices"
          item-title="name"
          item-value="id"
          label="Leave policy"
          :loading="policies.loading"
          v-bind="FIELD_PROPS"
        />
        <AppCallout v-if="error || policies.error" variant="error" class="mt-4">
          {{ error || policies.error }}
        </AppCallout>
      </div>
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" :disabled="moving" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="moving" :disabled="!target || unchanged" @click="submit">
          Move to {{ target?.name ?? 'policy' }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useEmployeesStore } from '@/stores/employees'
import { useLeaveAssignmentsStore } from '@/stores/leaveAssignments'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { EmployeeRecord } from '@/types/employee'
import type { AssignResult } from '@/types/leavePolicy'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'
import { MOVE_POLICY_BODY } from '@/utils/policyMembers'

const props = defineProps<{ record: EmployeeRecord }>()
const emit = defineEmits<{ moved: [result: AssignResult, policyName: string] }>()
const open = defineModel<boolean>({ required: true })

const policies = useLeavePoliciesStore()
const assignments = useLeaveAssignmentsStore()
const employees = useEmployeesStore()
const policyId = ref<string | null>(null)
const moving = ref(false)
const error = ref('')

const choices = computed(() =>
  policies.policies.map(p => ({ id: p.id, name: p.is_default ? `${p.name} (default)` : p.name })),
)
const target = computed(() => policies.policies.find(p => p.id === policyId.value) ?? null)
const unchanged = computed(() => props.record.leave_policy?.id === policyId.value)

watch(open, isOpen => {
  if (!isOpen) return
  error.value = ''
  policyId.value = props.record.leave_policy?.id ?? null
  if (!policies.policies.length) void policies.fetchPolicies()
})

async function submit(): Promise<void> {
  const policy = target.value
  if (!policy) return
  moving.value = true
  const result = await assignments.move(policy.id, [props.record.user_id])
  moving.value = false
  if (typeof result === 'string') {
    error.value = result
    return
  }
  if (result.assigned) {
    employees.setLeavePolicy(props.record.user_id, {
      id: policy.id,
      name: policy.name,
      is_default: policy.is_default,
      explicit: true,
    })
  }
  open.value = false
  emit('moved', result, policy.name)
}
</script>
