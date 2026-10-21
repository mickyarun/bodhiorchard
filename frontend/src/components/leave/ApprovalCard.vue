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

<!-- One request in the approvals queue: the request, the requester's
     balances by type (requested type highlighted), their last leave and who
     else is out. Rejecting asks for a note. -->
<template>
  <v-card color="surface" rounded="lg" class="pa-5">
    <div class="d-flex align-start justify-space-between ga-3 flex-wrap">
      <div class="min-w-0">
        <div class="text-body-1 font-weight-bold">{{ request.user.name }}</div>
        <div v-if="role" class="text-caption text-medium-emphasis">{{ role }}</div>
      </div>
      <span class="route-tag">{{ ROUTE_TAGS[item.route] }}</span>
    </div>

    <div class="d-flex align-center flex-wrap ga-2 mt-3">
      <v-icon :icon="request.kind === 'wfh' ? 'mdi-home-outline' : 'mdi-beach'" size="18" />
      <span class="text-body-2 font-weight-medium">{{ requestTypeLabel(request) }}</span>
      <span class="text-body-2 text-medium-emphasis">
        · {{ formatDayRange(request.start_date, request.end_date) }}
        · {{ pluralDays(toNumber(request.days)) }}
        <template v-if="request.half_day !== 'none'">({{ HALF_DAY_LABELS[request.half_day].toLowerCase() }})</template>
      </span>
    </div>
    <p v-if="request.reason" class="text-body-2 mt-2 reason">“{{ request.reason }}”</p>

    <AppCallout v-if="lop" variant="warning" class="mt-3">
      {{ lop }} of this request {{ toNumber(request.lop_days) === 1 ? 'is' : 'are' }} loss of pay:
      not enough {{ requestTypeLabel(request) }} left.
    </AppCallout>

    <template v-if="request.kind === 'leave' && item.balances.length">
      <div class="d-flex align-baseline flex-wrap ga-2 mt-4 mb-2">
        <span class="section-label">Balances · leave year {{ item.balance_year }}</span>
        <span class="text-caption text-medium-emphasis">{{ balanceNote }}</span>
      </div>
      <BalanceGrid :balances="item.balances" compact :highlight-type-id="inBalanceYear ? request.leave_type?.id : null" />
    </template>

    <ApprovalFacts :item="item" class="mt-3" />

    <div v-if="request.status !== 'pending'" class="d-flex align-center flex-wrap ga-2 mt-3">
      <LeaveStatusChip :status="request.status" />
      <span v-if="request.decided_by" class="text-caption text-medium-emphasis">
        by {{ request.decided_by.name }}
      </span>
      <span v-if="request.decision_note" class="text-caption">“{{ request.decision_note }}”</span>
    </div>

    <template v-else>
      <v-textarea
        v-if="rejecting"
        v-model="note"
        label="Why are you rejecting this?"
        hint="The requester sees this note."
        persistent-hint
        rows="2"
        auto-grow
        counter="500"
        maxlength="500"
        variant="outlined"
        density="compact"
        hide-details="auto"
        class="mt-4"
        autofocus
      />
      <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
      <div class="d-flex justify-end ga-2 mt-4">
        <template v-if="rejecting">
          <v-btn variant="text" @click="rejecting = false">Back</v-btn>
          <v-btn color="error" variant="tonal" :loading="busy" :disabled="!note.trim()" @click="decide('reject')">
            Reject request
          </v-btn>
        </template>
        <template v-else>
          <v-btn color="error" variant="tonal" :disabled="busy" @click="rejecting = true">Reject</v-btn>
          <v-btn color="success" variant="tonal" :loading="busy" @click="decide('approve')">Approve</v-btn>
        </template>
      </div>
    </template>
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import ApprovalFacts from '@/components/leave/ApprovalFacts.vue'
import BalanceGrid from '@/components/leave/BalanceGrid.vue'
import LeaveStatusChip from '@/components/leave/LeaveStatusChip.vue'
import { useLeaveApprovalsStore } from '@/stores/leaveApprovals'
import type { ApprovalItem } from '@/types/leave'
import { otherYearBalanceAfter } from '@/utils/approvalFacts'
import {
  HALF_DAY_LABELS,
  lopLabel,
  pluralDays,
  requestTypeLabel,
  ROUTE_TAGS,
  toNumber,
} from '@/utils/leave'
import { formatDayRange } from '@/utils/leaveDates'

const props = defineProps<{ item: ApprovalItem }>()

const store = useLeaveApprovalsStore()
const request = computed(() => props.item.request)
const rejecting = ref(false)
const note = ref('')
const busy = ref(false)
const error = ref('')

const role = computed(() =>
  [props.item.designation, props.item.department].filter(Boolean).join(' · '),
)

// Tiles show the current leave year; a request priced on another year
// isn't in them, so it isn't highlighted or called "included".
const inBalanceYear = computed(() => otherYearBalanceAfter(props.item) === null)
const balanceNote = computed(() =>
  inBalanceYear.value
    ? 'Pending requests, this one included, are counted.'
    : 'Pending requests are counted. This request falls in another leave year.',
)

// "3 days", from "3 days loss of pay".
const lop = computed(() => lopLabel(request.value.lop_days).replace(/ loss of pay$/, ''))

async function decide(action: 'approve' | 'reject'): Promise<void> {
  busy.value = true
  error.value =
    (action === 'approve'
      ? await store.approve(request.value.id, '')
      : await store.reject(request.value.id, note.value)) ?? ''
  busy.value = false
}
</script>

<style scoped>
.min-w-0 {
  min-width: 0;
}
.route-tag {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: var(--tracking-label, 0.08em);
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgb(var(--v-theme-primary));
}
.reason {
  color: rgba(var(--v-theme-on-surface), 0.78);
}
.section-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: var(--tracking-label, 0.08em);
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.7);
}
</style>
