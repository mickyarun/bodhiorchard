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

<!-- Settings → Leave (leave:configure). Policies set working days,
     holidays, leave types and WFH rules; People shows who follows which.
     `?view=people` picks the people list, `?policy=<id>` opens a policy. -->
<template>
  <div class="pa-6 settings-leave">
    <div class="d-flex align-start justify-space-between flex-wrap ga-3 mb-4">
      <div>
        <h1 class="text-h5 font-weight-bold bo-display">Leave</h1>
        <p class="text-body-2 text-medium-emphasis">
          Set leave types, holidays and rules per location, and choose who follows each.
        </p>
      </div>
      <v-btn v-if="!open && view === 'policies'" color="primary" prepend-icon="mdi-plus" @click="adding = true">
        Add policy
      </v-btn>
    </div>

    <AppPillToggle v-if="!open" v-model="view" :options="VIEW_OPTIONS" aria-label="Show" class="mb-6" />

    <v-progress-linear v-if="store.loading && !store.policies.length" indeterminate color="primary" class="mb-4" />
    <AppCallout v-if="store.error" variant="error" class="mb-4">{{ store.error }}</AppCallout>

    <PolicyDetail v-if="open" :policy="open" :region="regionOf(open)" @back="select(null)" />
    <PolicyListView v-else-if="view === 'policies'" @open="select" />
    <LeaveAssignmentsTable v-else />

    <AddPolicyDialog v-model="adding" @created="policy => select(policy.id)" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { type LocationQuery, useRoute, useRouter } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import AddPolicyDialog from '@/components/leave/settings/AddPolicyDialog.vue'
import LeaveAssignmentsTable from '@/components/leave/settings/LeaveAssignmentsTable.vue'
import PolicyDetail from '@/components/leave/settings/PolicyDetail.vue'
import PolicyListView from '@/components/leave/settings/PolicyListView.vue'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { PolicyRead } from '@/types/leavePolicy'
import { regionLabel } from '@/utils/leavePolicy'

type View = 'policies' | 'people'

const VIEW_OPTIONS: { label: string; value: View }[] = [
  { label: 'Policies', value: 'policies' },
  { label: 'People', value: 'people' },
]

const route = useRoute()
const router = useRouter()
const store = useLeavePoliciesStore()
const adding = ref(false)

const open = computed(() => store.policies.find(p => p.id === route.query.policy) ?? null)

const view = computed<View>({
  get: () => (route.query.view === 'people' ? 'people' : 'policies'),
  set: value => {
    const rest = queryWithout('view')
    void router.replace({ query: value === 'people' ? { ...rest, view: value } : rest })
  },
})

function queryWithout(...keys: string[]): LocationQuery {
  const query = { ...route.query }
  for (const key of keys) delete query[key]
  return query
}

function regionOf(policy: PolicyRead): string {
  return regionLabel(store.countries, policy.country_code, policy.subdivision_code)
}

/** Open a policy (its first section), or go back to the list. */
function select(id: string | null): void {
  const rest = queryWithout('policy', 'section', 'view')
  void router.replace({ query: id ? { ...rest, policy: id } : rest })
}

onMounted(() => {
  void store.fetchPolicies()
  void store.fetchCountries()
})
</script>

<style scoped>
.settings-leave {
  max-width: 1200px;
}
</style>
