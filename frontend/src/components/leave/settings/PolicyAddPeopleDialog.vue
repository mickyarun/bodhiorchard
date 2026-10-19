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

<!-- Move people onto this policy. Only people with an employee record can
     follow a policy, so the picker lists exactly those not already on it. -->
<template>
  <v-dialog v-model="open" max-width="560">
    <v-card color="surface" rounded="lg">
      <div class="pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">Add people to {{ policy.name }}</h2>
        <p class="text-body-2 text-medium-emphasis mt-2 mb-5">{{ MOVE_POLICY_BODY }}</p>
        <v-autocomplete
          v-model="chosen"
          v-model:search="typed"
          :items="candidates"
          item-title="name"
          item-value="user_id"
          return-object
          :item-props="itemProps"
          label="People"
          placeholder="Search by name or email"
          :custom-filter="matches"
          :loading="members.loading.value"
          multiple
          chips
          closable-chips
          autofocus
          v-bind="FIELD_PROPS"
        />
        <AppCallout v-if="members.error.value || error" variant="error" class="mt-4">
          {{ error || members.error.value }}
        </AppCallout>
      </div>
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" :disabled="moving" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="moving" :disabled="!chosen.length" @click="submit">
          {{ chosen.length ? `Move ${peopleCount(chosen.length)}` : 'Move people' }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useDebounced } from '@/composables/useDebounced'
import { usePolicyMembers } from '@/composables/usePolicyMembers'
import { useAuthStore } from '@/stores/auth'
import { useLeaveAssignmentsStore } from '@/stores/leaveAssignments'
import type { AssignResult, PolicyMemberRead, PolicyRead } from '@/types/leavePolicy'
import { FIELD_PROPS, peopleCount } from '@/utils/leavePolicyDisplay'
import {
  ALL_POLICIES,
  canChangeMemberPolicy,
  memberQuery,
  MOVE_POLICY_BODY,
  OWN_POLICY_HINT,
} from '@/utils/policyMembers'

const props = defineProps<{ policy: PolicyRead }>()
const emit = defineEmits<{ moved: [result: AssignResult] }>()
const open = defineModel<boolean>({ required: true })

const store = useLeaveAssignmentsStore()
const authStore = useAuthStore()
const { isOrgOwner } = usePermissions()
const typed = ref('')
const searched = useDebounced(typed)
// The server searches, so anyone can be found however long the list is.
const query = computed(() => memberQuery(ALL_POLICIES, searched.value))
const members = usePolicyMembers(query, open)
// Whole rows, so chips keep their names when a new search replaces the list.
const chosen = ref<PolicyMemberRead[]>([])
const moving = ref(false)
const error = ref('')

const candidates = computed(() => members.rows.value.filter(m => m.policy_id !== props.policy.id))

function itemProps(member: PolicyMemberRead): Record<string, unknown> {
  const allowed = canChangeMemberPolicy(member.user_id, authStore.user?.id, isOrgOwner.value)
  return {
    subtitle: allowed ? `${member.email} · on ${member.policy_name}` : OWN_POLICY_HINT,
    disabled: !allowed,
  }
}

function matches(_title: string, search: string, item?: { raw: PolicyMemberRead }): boolean {
  const term = search.trim().toLowerCase()
  if (!term || !item) return true
  return `${item.raw.name} ${item.raw.email}`.toLowerCase().includes(term)
}

watch(open, isOpen => {
  if (!isOpen) return
  chosen.value = []
  typed.value = ''
  error.value = ''
})

async function submit(): Promise<void> {
  if (!chosen.value.length) return
  moving.value = true
  const result = await store.move(
    props.policy.id,
    chosen.value.map(m => m.user_id),
  )
  moving.value = false
  if (typeof result === 'string') {
    error.value = result
    return
  }
  open.value = false
  emit('moved', result)
}
</script>
