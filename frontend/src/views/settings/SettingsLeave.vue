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

<!-- Settings → Leave (leave:configure): leave policies. A policy sets
     working days, holidays, leave types and WFH rules for the people on
     it. `?policy=<id>` opens one. -->
<template>
  <div class="pa-6 settings-leave">
    <div class="d-flex align-start justify-space-between flex-wrap ga-3 mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold bo-display">Leave</h1>
        <p class="text-body-2 text-medium-emphasis">
          Policies set working days, holidays, leave types and work-from-home rules for the people on them.
        </p>
      </div>
      <v-btn v-if="!open" color="primary" prepend-icon="mdi-plus" @click="adding = true">Add policy</v-btn>
    </div>

    <v-progress-linear v-if="store.loading && !store.policies.length" indeterminate color="primary" class="mb-4" />
    <AppCallout v-if="store.error || actionError" variant="error" class="mb-4">
      {{ actionError || store.error }}
    </AppCallout>

    <PolicyDetail v-if="open" :policy="open" :region="regionOf(open)" @back="select(null)" />

    <template v-else>
      <SlackLeaveCard />
      <p v-if="!store.loading && !store.policies.length && !store.error" class="text-body-2 text-medium-emphasis">
        No policies yet. Add one to set up leave types and holidays.
      </p>
      <div class="policy-grid">
        <PolicyCard
          v-for="policy in store.policies"
          :key="policy.id"
          :policy="policy"
          :region="regionOf(policy)"
          :busy="busyId === policy.id"
          @open="select(policy.id)"
          @make-default="makeDefault(policy.id)"
          @delete="deleting = policy"
        />
      </div>
    </template>

    <AddPolicyDialog v-model="adding" @created="policy => select(policy.id)" />
    <ConfirmDialog
      :model-value="!!deleting"
      title="Delete this policy?"
      :message="`${deleting?.name ?? ''} and its leave types and holidays will be removed.`"
      confirm-label="Delete policy"
      icon="mdi-delete-outline"
      @update:model-value="value => !value && (deleting = null)"
      @confirm="remove"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import AddPolicyDialog from '@/components/leave/settings/AddPolicyDialog.vue'
import PolicyCard from '@/components/leave/settings/PolicyCard.vue'
import PolicyDetail from '@/components/leave/settings/PolicyDetail.vue'
import SlackLeaveCard from '@/components/leave/settings/SlackLeaveCard.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { PolicyRead } from '@/types/leavePolicy'
import { regionLabel } from '@/utils/leavePolicy'

const route = useRoute()
const router = useRouter()
const store = useLeavePoliciesStore()
const adding = ref(false)
const deleting = ref<PolicyRead | null>(null)
const busyId = ref<string | null>(null)
const actionError = ref('')

const open = computed(() => store.policies.find(p => p.id === route.query.policy) ?? null)

function regionOf(policy: PolicyRead): string {
  return regionLabel(store.countries, policy.country_code, policy.subdivision_code)
}

function select(id: string | null): void {
  actionError.value = ''
  const query = { ...route.query }
  if (id) query.policy = id
  else delete query.policy
  void router.replace({ query })
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

onMounted(() => {
  void store.fetchPolicies()
  void store.fetchCountries()
})
</script>

<style scoped>
.settings-leave {
  max-width: 1120px;
}
.policy-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
</style>
