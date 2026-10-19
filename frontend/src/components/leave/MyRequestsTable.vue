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

<!-- "My requests" on Leave home: upcoming / past / all, with cancel. -->
<template>
  <section>
    <div class="d-flex align-center justify-space-between flex-wrap ga-3 mb-3">
      <h2 class="text-subtitle-1 font-weight-bold">My requests</h2>
      <AppPillToggle :model-value="store.scope" :options="SCOPES" size="sm" @update:model-value="store.fetchRequests" />
    </div>
    <AppCallout v-if="store.requestsError || cancelError" variant="error" class="mb-3">
      {{ cancelError || store.requestsError }}
    </AppCallout>
    <v-card color="surface" rounded="lg">
      <v-progress-linear v-if="store.requestsLoading" indeterminate color="primary" />
      <div v-if="!store.requestsLoading && !store.requests.length" class="pa-6 text-body-2 text-medium-emphasis">
        {{ emptyText }}
      </div>
      <v-table v-else density="comfortable">
        <thead>
          <tr>
            <th>Dates</th>
            <th>Type</th>
            <th>Days</th>
            <th>Status</th>
            <th>Approver</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in store.requests" :key="row.id">
            <td>
              <div class="font-weight-medium">{{ formatDayRange(row.start_date, row.end_date) }}</div>
              <div v-if="row.half_day !== 'none'" class="text-caption text-medium-emphasis">
                {{ HALF_DAY_LABELS[row.half_day] }}
              </div>
            </td>
            <td>{{ requestTypeLabel(row) }}</td>
            <td>{{ formatDays(toNumber(row.days)) }}</td>
            <td><LeaveStatusChip :status="row.status" /></td>
            <td>
              <div>{{ approverLabel(row) }}</div>
              <div v-if="row.status === 'rejected' && row.decision_note" class="text-caption text-medium-emphasis">
                “{{ row.decision_note }}”
              </div>
            </td>
            <td class="text-right">
              <v-btn v-if="row.can_cancel" variant="text" size="small" @click="confirming = row">Cancel</v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>
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
import LeaveStatusChip from '@/components/leave/LeaveStatusChip.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { useLeaveStore } from '@/stores/leave'
import type { LeaveRequestRead, RequestScope } from '@/types/leave'
import { formatDays, HALF_DAY_LABELS, requestTypeLabel, toNumber } from '@/utils/leave'
import { formatDayRange } from '@/utils/leaveDates'

const props = defineProps<{ pendingWith: string }>()
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

function approverLabel(row: LeaveRequestRead): string {
  if (row.approval_mode === 'auto_policy') return 'Approved automatically'
  if (row.decided_by) return row.decided_by.name
  return row.status === 'pending' ? props.pendingWith : '—'
}

async function cancel(): Promise<void> {
  const row = confirming.value
  confirming.value = null
  if (!row) return
  cancelError.value = (await store.cancelRequest(row.id)) ?? ''
  if (!cancelError.value) emit('cancelled')
}
</script>

