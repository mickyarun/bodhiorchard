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

<!-- Who can request a leave type, whether it approves itself, and a
     per-month limit (unused days don't carry into the next month). -->
<template>
  <div class="access">
    <div class="who">
      <span class="text-body-2 font-weight-medium">Who can use it</span>
      <AppPillToggle v-model="eligibility" :options="WHO" aria-label="Who can use it" />
    </div>
    <p class="text-caption text-medium-emphasis">
      {{ eligibility === 'women' ? "Only people whose profile gender is Female see it. Set gender on each person's Personal tab." : 'Everyone on the policy.' }}
    </p>
    <LeaveSwitchRow v-model="autoApprove" label="Approve automatically" description="Approved as soon as it's sent, unless it would be unpaid. Managers get a heads-up." />
    <LeaveSwitchRow v-model="limited" label="Limit days per month" description="Unused days don't carry into the next month." />
    <v-text-field
      v-if="limited"
      v-model.number="perMonth"
      label="Most days in a month"
      type="number"
      min="0.5"
      max="31"
      step="0.5"
      suffix="days"
      class="per-month"
      v-bind="FIELD_PROPS"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import LeaveSwitchRow from '@/components/leave/settings/LeaveSwitchRow.vue'
import type { Decimalish, LeaveEligibility } from '@/types/leave'
import { toNumberOrNull } from '@/utils/leave'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const eligibility = defineModel<LeaveEligibility>('eligibility', { required: true })
const autoApprove = defineModel<boolean>('autoApprove', { required: true })
const monthlyLimit = defineModel<Decimalish | null>('monthlyLimit', { required: true })

const WHO: { label: string; value: LeaveEligibility }[] = [
  { label: 'Everyone', value: 'everyone' },
  { label: 'Women only', value: 'women' },
]

const limited = computed<boolean>({
  get: () => monthlyLimit.value !== null,
  set: on => {
    monthlyLimit.value = on ? 1 : null
  },
})

const perMonth = computed<number | null>({
  get: () => (monthlyLimit.value === '' ? null : toNumberOrNull(monthlyLimit.value)),
  set: value => {
    // Empty while typing stays empty (not null, which would switch the limit off).
    monthlyLimit.value = typeof value === 'number' ? value : ''
  },
})
</script>

<style scoped>
.who {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}
.per-month {
  max-width: 220px;
  margin-top: 4px;
}
</style>
