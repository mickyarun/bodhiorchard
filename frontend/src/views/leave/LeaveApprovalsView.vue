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

<!-- Leave approvals: requests from the caller's reports, plus the HR
     queue for holders of leave:approve. -->
<template>
  <div class="pa-6 approvals">
    <div class="d-flex align-start justify-space-between flex-wrap ga-3 mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold bo-display">Leave approvals</h1>
        <p class="text-body-2 text-medium-emphasis">
          Approve or reject leave and work-from-home requests.
        </p>
      </div>
      <AppPillToggle :model-value="store.status" :options="TABS" @update:model-value="store.fetch" />
    </div>

    <ApprovalFilters class="mb-4" />
    <v-progress-linear v-if="store.loading" indeterminate color="primary" class="mb-4" />
    <AppCallout v-if="store.error" variant="error" class="mb-4">{{ store.error }}</AppCallout>
    <AppCallout v-if="store.notice" variant="info" class="mb-4">{{ store.notice }}</AppCallout>

    <div v-if="!store.loading && !store.error && !store.items.length" class="empty">
      <v-icon icon="mdi-check-all" size="32" color="success" />
      <div class="text-body-1 font-weight-medium mt-2">
        {{ emptyTitle }}
      </div>
      <div class="text-body-2 text-medium-emphasis">
        {{ store.status === 'pending' ? 'New requests show here.' : 'Requests approved or rejected recently show here.' }}
      </div>
    </div>

    <AppCallout v-if="showLimitHint" variant="info" class="mb-4">
      Showing the latest {{ store.items.length }} decisions.
      {{ dated ? 'Narrow the dates or filters to see the rest.' : 'Pick dates to find older ones.' }}
    </AppCallout>
    <div class="d-flex flex-column ga-3">
      <ApprovalCard v-for="item in store.items" :key="item.request.id" :item="item" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import ApprovalCard from '@/components/leave/ApprovalCard.vue'
import ApprovalFilters from '@/components/leave/ApprovalFilters.vue'
import { useDebounced } from '@/composables/useDebounced'
import { type ApprovalTab, useLeaveApprovalsStore } from '@/stores/leaveApprovals'

const store = useLeaveApprovalsStore()
// Before the filter bar sets up, so it never shows another viewer's picks.
store.forgetPreviousViewer()
const TABS: { label: string; value: ApprovalTab }[] = [
  { label: 'Pending', value: 'pending' },
  { label: 'Decided', value: 'decided' },
]

const filtered = computed(() => Object.values(store.filters).some(Boolean))
const emptyTitle = computed(() => {
  if (filtered.value) return 'Nothing matches these filters'
  return store.status === 'pending' ? "You're all caught up" : 'No decisions yet'
})
// The cap applies with or without dates; dates only lift the 90-day window.
const dated = computed(() => !!(store.filters.start || store.filters.end))
const showLimitHint = computed(() => store.status === 'decided' && store.truncated)

// One request per settled change, not one per keystroke in a custom date.
const query = ref('')
const settled = useDebounced(query)
watch(
  () => JSON.stringify(store.filters),
  value => {
    query.value = value
  },
)
watch(settled, () => {
  void store.fetch()
})

onMounted(() => {
  void store.fetch()
})
</script>

<style scoped>
.approvals {
  max-width: 1120px;
}
.empty {
  text-align: center;
  padding: 48px 16px;
}
</style>
