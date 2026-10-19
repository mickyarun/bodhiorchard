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

<!-- Leave home: the caller's balances and requests. The landing page for
     every member outside the engineering workspace (sales, HR). -->
<template>
  <div class="pa-6 leave-home">
    <div class="d-flex align-start justify-space-between flex-wrap ga-3 mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold bo-display">Leave</h1>
        <p class="text-body-2 text-medium-emphasis">{{ subtitle }}</p>
      </div>
      <div class="d-flex flex-wrap ga-2">
        <v-btn color="primary" prepend-icon="mdi-plus" :disabled="!summary" @click="open('leave')">
          Request leave
        </v-btn>
        <v-btn
          v-if="summary?.work_arrangement !== 'remote'"
          variant="tonal"
          prepend-icon="mdi-home-outline"
          :disabled="!summary"
          @click="open('wfh')"
        >
          Work from home
        </v-btn>
        <v-btn variant="text" prepend-icon="mdi-calendar-month-outline" :to="{ name: 'leave-team' }">
          Team calendar
        </v-btn>
      </div>
    </div>

    <v-progress-linear v-if="store.summaryLoading && !summary" indeterminate color="primary" class="mb-4" />
    <AppCallout v-if="store.summaryError" variant="error" class="mb-4">{{ store.summaryError }}</AppCallout>

    <template v-if="summary">
      <AppCallout v-if="!summary.balances.length && canConfigureLeave" variant="info" class="mb-6">
        No leave types yet. Add them so people can request leave.
        <template #actions>
          <v-btn size="small" variant="tonal" color="primary" :to="{ name: 'settings-leave' }">
            Set up leave types
          </v-btn>
        </template>
      </AppCallout>
      <AppCallout v-else-if="!summary.balances.length" variant="info" class="mb-6">
        {{ noTypesText }}
      </AppCallout>
      <BalanceGrid
        v-else
        :balances="summary.balances"
        :optional="summary.optional_holidays"
        class="mb-8"
      />
    </template>

    <MyRequestsTable :pending-with="pendingWith" @cancelled="notify('Request cancelled')" />

    <LeaveRequestDialog v-model="dialogOpen" :preset="preset" @sent="notify('Request sent')" />
    <v-snackbar v-model="snackbar" color="success" :timeout="3000">{{ snackbarText }}</v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import BalanceGrid from '@/components/leave/BalanceGrid.vue'
import LeaveRequestDialog from '@/components/leave/LeaveRequestDialog.vue'
import MyRequestsTable from '@/components/leave/MyRequestsTable.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useLeaveStore } from '@/stores/leave'
import type { LeaveKind } from '@/types/leave'
import { joinWithAnd } from '@/utils/leave'
import { formatLeaveYear } from '@/utils/leaveDates'

const store = useLeaveStore()
const { canConfigureLeave } = usePermissions()

const summary = computed(() => store.summary)
const dialogOpen = ref(false)
const preset = ref<LeaveKind>('leave')
const snackbar = ref(false)
const snackbarText = ref('')

const noTypesText = computed(() =>
  summary.value?.work_arrangement === 'remote'
    ? "HR hasn't added leave types yet, so there's nothing to request."
    : "HR hasn't added leave types yet. You can still request work from home.",
)

const subtitle = computed(() => {
  if (!summary.value) return 'Request leave and work from home, and see who’s out.'
  return `Leave year ${formatLeaveYear(summary.value.leave_year)} · ${summary.value.policy.name}`
})

const pendingWith = computed(() => {
  if (!summary.value || summary.value.routes_to_hr || !summary.value.approvers.length) {
    return 'Waiting on HR'
  }
  return `Waiting on ${joinWithAnd(summary.value.approvers.map(a => a.name))}`
})

function open(kind: LeaveKind): void {
  preset.value = kind
  dialogOpen.value = true
}

function notify(text: string): void {
  snackbarText.value = text
  snackbar.value = true
}

onMounted(() => {
  void store.fetchSummary()
  void store.fetchRequests()
})
</script>

<style scoped>
.leave-home {
  max-width: 1120px;
}
</style>
