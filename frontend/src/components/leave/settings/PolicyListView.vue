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

<!-- Settings → Leave → Policies: the Slack settings, then every policy as
     a card. Making one the default and deleting live in each card's menu. -->
<template>
  <section aria-label="Policies">
    <SlackLeaveCard />
    <AppCallout v-if="actionError" variant="error" class="mb-4">{{ actionError }}</AppCallout>
    <AppCallout v-if="store.defaultPolicy" variant="info" class="mb-4">
      <strong>{{ store.defaultPolicy.name }}</strong> is the default policy. Anyone you haven't
      assigned follows it.
    </AppCallout>
    <LeaveEmptyState
      v-if="!store.loading && !store.policies.length && !store.error"
      icon="mdi-file-document-outline"
      title="No policies yet"
      body="Add one to set up leave types and holidays."
    />
    <div class="policy-grid">
      <PolicyCard
        v-for="policy in store.policies"
        :key="policy.id"
        :policy="policy"
        :region="regionOf(policy)"
        :busy="busyId === policy.id"
        @open="emit('open', policy.id)"
        @make-default="makeDefault(policy.id)"
        @delete="deleting = policy"
      />
    </div>
    <ConfirmDialog
      :model-value="!!deleting"
      title="Delete this policy?"
      :message="`${deleting?.name ?? ''} and its leave types and holidays will be removed.`"
      confirm-label="Delete policy"
      icon="mdi-delete-outline"
      @update:model-value="value => !value && (deleting = null)"
      @confirm="remove"
    />
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import PolicyCard from '@/components/leave/settings/PolicyCard.vue'
import SlackLeaveCard from '@/components/leave/settings/SlackLeaveCard.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { PolicyRead } from '@/types/leavePolicy'
import { regionLabel } from '@/utils/leavePolicy'

const emit = defineEmits<{ open: [id: string] }>()

const store = useLeavePoliciesStore()
const deleting = ref<PolicyRead | null>(null)
const busyId = ref<string | null>(null)
const actionError = ref('')

function regionOf(policy: PolicyRead): string {
  return regionLabel(store.countries, policy.country_code, policy.subdivision_code)
}

async function makeDefault(id: string): Promise<void> {
  busyId.value = id
  actionError.value = (await store.makeDefault(id)) ?? ''
  busyId.value = null
}

async function remove(): Promise<void> {
  const policy = deleting.value
  deleting.value = null
  if (policy) actionError.value = (await store.deletePolicy(policy.id)) ?? ''
}
</script>

<style scoped>
.policy-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
@media (max-width: 400px) {
  .policy-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
