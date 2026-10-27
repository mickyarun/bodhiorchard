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

<!-- My leave: the caller's balances and requests, who else is out this
     week and how their policy works. The landing page for every member
     outside the engineering workspace (sales, HR). -->
<template>
  <AppPage title="My leave" :subtitle="subtitle">
    <template #actions>
      <v-btn variant="text" :to="{ name: 'leave-team' }">Team calendar</v-btn>
      <v-btn v-if="summary?.work_arrangement !== 'remote'" variant="outlined" :disabled="!summary" @click="open('wfh')">
        Work from home
      </v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" :disabled="!summary" @click="open('leave')">
        Request leave
      </v-btn>
    </template>

    <SlackStatusConnect />
    <v-progress-linear v-if="store.summaryLoading && !summary" indeterminate color="primary" />
    <AppCallout v-if="store.summaryError" variant="error">{{ store.summaryError }}</AppCallout>

    <template v-if="summary">
      <AppCallout v-if="summary.high_leave" :variant="highLeaveVariant(summary.high_leave)">
        {{ highLeaveForSelf(summary.high_leave, false) }}
      </AppCallout>
      <AppCallout v-if="!summary.balances.length && canConfigureLeave" variant="info">
        No leave types yet. Add them so people can request leave.
        <template #actions>
          <v-btn size="small" variant="outlined" :to="{ name: 'settings-leave' }">Set up leave types</v-btn>
        </template>
      </AppCallout>
      <AppCallout v-else-if="!summary.balances.length" variant="info">{{ noTypesText }}</AppCallout>
      <BalanceGrid
        v-else
        :balances="summary.balances"
        :optional="summary.optional_holidays"
        :lop-days="summary.lop_days"
      />
    </template>

    <div class="leave-home__columns">
      <MyRequestsTable :pending-with="pendingWith" @cancelled="notify('Request cancelled')" />
      <aside class="leave-home__aside">
        <OutSoonPanel />
        <PolicyNotesPanel v-if="summary" :summary="summary" />
      </aside>
    </div>

    <LeaveRequestPanel v-model="panelOpen" :preset="preset" @sent="notify('Request sent')" />
    <v-snackbar v-model="snackbar" color="success" :timeout="3000">{{ snackbarText }}</v-snackbar>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import BalanceGrid from '@/components/leave/BalanceGrid.vue'
import LeaveRequestPanel from '@/components/leave/LeaveRequestPanel.vue'
import MyRequestsTable from '@/components/leave/MyRequestsTable.vue'
import OutSoonPanel from '@/components/leave/OutSoonPanel.vue'
import PolicyNotesPanel from '@/components/leave/PolicyNotesPanel.vue'
import SlackStatusConnect from '@/components/leave/SlackStatusConnect.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useLeaveStore } from '@/stores/leave'
import type { LeaveKind } from '@/types/leave'
import { highLeaveForSelf, highLeaveVariant } from '@/utils/highLeave'
import { formatLeaveYear } from '@/utils/leaveDates'
import { approversOf } from '@/utils/leaveHome'

const store = useLeaveStore()
const { canConfigureLeave } = usePermissions()

const summary = computed(() => store.summary)
const panelOpen = ref(false)
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

const pendingWith = computed(() => `Waiting on ${approversOf(summary.value)}`)

function open(kind: LeaveKind): void {
  preset.value = kind
  panelOpen.value = true
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
.leave-home__columns {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
.leave-home__aside {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
@media (max-width: 1100px) {
  .leave-home__columns {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
