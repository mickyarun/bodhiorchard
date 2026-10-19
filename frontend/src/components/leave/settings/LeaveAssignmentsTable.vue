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

<!-- Every employee and the leave policy they follow; select people and
     move them to another policy. With `pinnedPolicyId` it lists only that
     policy's people (the policy's People section). -->
<template>
  <section aria-label="People and their leave policies">
    <AssignmentToolbar v-model:search="search" v-model:filter="filter" :filter-items="pinnedPolicyId ? undefined : filterItems" />
    <AppCallout v-if="members.error.value" variant="error" class="mb-4">{{ members.error.value }}</AppCallout>
    <AppCallout v-if="notice" :variant="notice.variant" class="mb-4">{{ notice.text }}</AppCallout>
    <AppCallout v-if="truncated" variant="info" class="mb-4">
      Showing the first {{ rows.length }} people. Search or pick a policy to narrow the list.
    </AppCallout>
    <v-data-table
      v-model="selected"
      :headers="HEADERS"
      :items="rows"
      item-value="user_id"
      :item-selectable="isSelectable"
      show-select
      :loading="members.loading.value"
      :items-per-page="25"
      density="comfortable"
      hover
      class="bg-transparent"
    >
      <template #[`item.data-table-select`]="{ internalItem, isSelected, toggleSelect }">
        <MemberSelectCell
          :name="internalItem.raw.name"
          :selectable="isSelectable(internalItem.raw)"
          :selected="isSelected(internalItem)"
          @toggle="toggleSelect(internalItem)"
        />
      </template>
      <template #[`item.name`]="{ item }">
        <div class="py-2">
          <div class="font-weight-medium">{{ item.name }}</div>
          <div class="text-caption text-medium-emphasis">{{ item.email }}</div>
        </div>
      </template>
      <template #[`item.department`]="{ item }">{{ item.department || '—' }}</template>
      <template #[`item.policy_name`]="{ item }"><MemberPolicyCell :member="item" /></template>
      <template #[`item.assigned_on`]="{ item }">{{ policySinceLabel(item) }}</template>
      <template #no-data>
        <LeaveEmptyState
          v-if="search || filter !== ALL_POLICIES"
          icon="mdi-account-search-outline"
          title="Nobody matches"
          body="Try another name, or a different policy."
        />
        <LeaveEmptyState
          v-else
          icon="mdi-account-multiple-outline"
          :title="pinnedPolicyId ? 'Nobody follows this policy yet' : 'No employee records yet'"
          :body="pinnedPolicyId ? 'Use Add people to move people onto it.' : 'People need an employee record before they can follow a leave policy.'"
        >
          <template v-if="!pinnedPolicyId" #actions>
            <v-btn variant="flat" color="primary" :to="{ name: 'employees' }">Go to employees</v-btn>
          </template>
        </LeaveEmptyState>
      </template>
    </v-data-table>
    <AssignmentBulkBar :count="selected.length" :policies="targets" @move="startMove" @clear="selected = []" />
    <MovePolicyDialog v-model="moveOpen" :policy="moveTarget" :user-ids="selected" @moved="onMoved" />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AssignmentBulkBar from '@/components/leave/settings/AssignmentBulkBar.vue'
import AssignmentToolbar from '@/components/leave/settings/AssignmentToolbar.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import MemberPolicyCell from '@/components/leave/settings/MemberPolicyCell.vue'
import MemberSelectCell from '@/components/leave/settings/MemberSelectCell.vue'
import MovePolicyDialog from '@/components/leave/settings/MovePolicyDialog.vue'
import { usePermissions } from '@/composables/usePermissions'
import { usePolicyMembers } from '@/composables/usePolicyMembers'
import { useAuthStore } from '@/stores/auth'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { AssignResult, PolicyMemberRead, PolicyRead } from '@/types/leavePolicy'
import { movedSummary, movedVariant } from '@/utils/leavePolicy'
import {
  ALL_POLICIES,
  canChangeMemberPolicy,
  isTruncated,
  memberFilterItems,
  memberQuery,
  policySinceLabel,
} from '@/utils/policyMembers'

const props = defineProps<{ pinnedPolicyId?: string }>()

const HEADERS = [
  { title: 'Name', key: 'name' },
  { title: 'Department', key: 'department' },
  { title: 'Leave policy', key: 'policy_name' },
  { title: 'On policy since', key: 'assigned_on', sortable: false },
] as const

const policies = useLeavePoliciesStore()
const authStore = useAuthStore()
const { isOrgOwner } = usePermissions()
const search = ref('')
const filter = ref(ALL_POLICIES)
const selected = ref<string[]>([])
const moveOpen = ref(false)
const moveTarget = ref<PolicyRead | null>(null)
const notice = ref<{ text: string; variant: 'success' | 'warning' } | null>(null)

const query = computed(() => memberQuery(props.pinnedPolicyId ?? filter.value, search.value))
const members = usePolicyMembers(query)
const rows = computed(() => members.rows.value)
const truncated = computed(() => isTruncated(rows.value, query.value))
const filterItems = computed(() => memberFilterItems(policies.policies))
const targets = computed(() => policies.policies.filter(p => p.id !== props.pinnedPolicyId))

function isSelectable(row: PolicyMemberRead): boolean {
  return canChangeMemberPolicy(row.user_id, authStore.user?.id, isOrgOwner.value)
}

function startMove(policy: PolicyRead): void {
  moveTarget.value = policy
  moveOpen.value = true
}

function onMoved(result: AssignResult): void {
  notice.value = {
    text: movedSummary(result, moveTarget.value?.name),
    variant: movedVariant(result),
  }
  selected.value = []
}

watch(() => JSON.stringify(query.value), () => {
  selected.value = []
})

onMounted(() => {
  if (!policies.policies.length) void policies.fetchPolicies()
})
</script>
