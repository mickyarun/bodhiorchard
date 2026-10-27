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

<!-- "My requests" on My leave: upcoming / past / all, as a list with a
     cancel option on each request that can still be cancelled. -->
<template>
  <section class="requests" aria-labelledby="my-requests-heading">
    <div class="requests__head">
      <h2 id="my-requests-heading" class="requests__title">My requests</h2>
      <AppPillToggle
        :model-value="store.scope"
        :options="SCOPES"
        size="sm"
        aria-label="Show"
        @update:model-value="store.fetchRequests"
      />
    </div>
    <AppCallout v-if="store.requestsError || cancelError" variant="error" class="mx-5 mb-3">
      {{ cancelError || store.requestsError }}
    </AppCallout>
    <v-progress-linear v-if="store.requestsLoading" indeterminate color="primary" />
    <p v-if="!store.requestsLoading && !store.requests.length" class="requests__empty">{{ emptyText }}</p>
    <ul v-else class="requests__list">
      <MyRequestRow
        v-for="row in store.requests"
        :key="row.id"
        :row="row"
        :pending-with="pendingWith"
        @cancel="confirming = $event"
      />
    </ul>
    <ConfirmDialog
      :model-value="!!confirming"
      title="Cancel this request?"
      :message="confirmMessage"
      confirm-label="Cancel request"
      cancel-label="Keep it"
      icon="mdi-cancel"
      @update:model-value="value => !value && (confirming = null)"
      @confirm="cancel"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import MyRequestRow from '@/components/leave/MyRequestRow.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { useLeaveStore } from '@/stores/leave'
import type { LeaveRequestRead, RequestScope } from '@/types/leave'
import { requestTypeLabel } from '@/utils/leave'
import { formatDayRange } from '@/utils/leaveDates'

defineProps<{ pendingWith: string }>()
const emit = defineEmits<(e: 'cancelled') => void>()

const store = useLeaveStore()
const SCOPES: { label: string; value: RequestScope }[] = [
  { label: 'Upcoming', value: 'upcoming' },
  { label: 'Past', value: 'past' },
  { label: 'All', value: 'all' },
]
const confirming = ref<LeaveRequestRead | null>(null)
const cancelError = ref('')

const emptyText = computed(() =>
  store.scope === 'upcoming' ? 'Nothing coming up. Requests you send show here.' : 'No requests yet.',
)
const confirmMessage = computed(() => {
  const row = confirming.value
  if (!row) return ''
  const days = formatDayRange(row.start_date, row.end_date)
  return row.status === 'approved'
    ? `${requestTypeLabel(row)} on ${days} is already approved. Cancelling gives the days back.`
    : `${requestTypeLabel(row)} on ${days} won't go to your approvers.`
})

async function cancel(): Promise<void> {
  const row = confirming.value
  confirming.value = null
  if (!row) return
  cancelError.value = (await store.cancelRequest(row.id)) ?? ''
  if (!cancelError.value) emit('cancelled')
}
</script>


<style scoped>
.requests {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  overflow: hidden;
  min-width: 0;
}
.requests__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 16px 20px;
}
.requests__title {
  margin: 0;
  flex-grow: 1;
  font-size: var(--text-base);
  font-weight: 600;
}
.requests__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.requests__empty {
  margin: 0;
  padding: 20px;
  border-top: 1px solid rgb(var(--v-theme-rule));
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
@media (max-width: 600px) {
  .requests__head {
    padding: 14px 16px;
  }
}
</style>
