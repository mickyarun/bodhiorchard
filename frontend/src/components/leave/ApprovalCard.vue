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

<!-- The selected request in the approvals queue: who and what, their
     reason, warnings, their balances by type (requested type highlighted),
     their last leave and who else is out, then the decision. Decided
     requests show the outcome and, while allowed, ways to change it. -->
<template>
  <section class="approval" :aria-labelledby="headingId">
    <ApprovalHeader :item="item" :heading-id="headingId" />

    <AppCallout v-if="lop" variant="warning">
      {{ lop }} of this request {{ toNumber(request.lop_days) === 1 ? 'is' : 'are' }} loss of pay:
      not enough {{ requestTypeLabel(request) }} left.
    </AppCallout>
    <AppCallout v-if="item.high_leave" :variant="highLeaveVariant(item.high_leave)">
      {{ highLeaveForOthers(item.high_leave, firstName(request.user.name)) }}
    </AppCallout>

    <div v-if="request.kind === 'leave' && item.balances.length" class="approval__section">
      <h3 class="approval__label">Balances · leave year {{ item.balance_year }}</h3>
      <p class="approval__note">{{ balanceNote }}</p>
      <BalanceGrid :balances="item.balances" compact :highlight-type-id="sameYear ? request.leave_type?.id : null" />
    </div>

    <ApprovalFacts :item="item" />

    <p v-if="decidedLine" class="approval__decided">{{ decidedLine }}</p>
    <ApprovedLeaveActions v-if="request.status !== 'pending' && request.can_change" :request="request" />
    <ApprovalDecision v-if="request.status === 'pending'" :request="request" />
  </section>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import ApprovalDecision from '@/components/leave/ApprovalDecision.vue'
import ApprovalFacts from '@/components/leave/ApprovalFacts.vue'
import ApprovalHeader from '@/components/leave/ApprovalHeader.vue'
import ApprovedLeaveActions from '@/components/leave/ApprovedLeaveActions.vue'
import BalanceGrid from '@/components/leave/BalanceGrid.vue'
import type { ApprovalItem } from '@/types/leave'
import { inBalanceYear } from '@/utils/approvalFacts'
import {
  firstName,
  lopLabel,
  requestTypeLabel,
  STATUS_META,
  toNumber,
} from '@/utils/leave'
import { highLeaveForOthers, highLeaveVariant } from '@/utils/highLeave'

const props = defineProps<{ item: ApprovalItem }>()

const headingId = useId()

/** Move focus to the requester's name, e.g. after picking this request. */
function focusHeading(): void {
  document.getElementById(headingId)?.focus()
}
defineExpose({ focusHeading })
const request = computed(() => props.item.request)

// Tiles show the current leave year; a request priced on another year
// isn't in them, so it isn't highlighted or called "included".
const sameYear = computed(() => inBalanceYear(props.item))
const balanceNote = computed(() =>
  sameYear.value
    ? 'Pending requests, this one included, are counted.'
    : 'Pending requests are counted. This request falls in another leave year.',
)

// "Approved by Kavya Nair · “Enjoy”". A cancelled request keeps its
// approver, so it doesn't say who cancelled it.
const decidedLine = computed(() => {
  const r = request.value
  if (r.status === 'pending') return ''
  const parts: string[] = []
  if (r.decided_by && r.status !== 'cancelled') parts.push(`${STATUS_META[r.status].label} by ${r.decided_by.name}`)
  if (r.decision_note) parts.push(`“${r.decision_note}”`)
  return parts.join(' · ')
})

// "3 days", from "3 days loss of pay".
const lop = computed(() => lopLabel(request.value.lop_days).replace(/ loss of pay$/, ''))

</script>

<style scoped>
.approval {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.approval__note,
.approval__decided {
  margin: 0;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.approval__section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.approval__label {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
}
@media (max-width: 600px) {
  .approval {
    padding: 18px 16px;
  }
}
</style>
