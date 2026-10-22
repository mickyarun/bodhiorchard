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

<!-- A leave type's allowance: a fixed number of days each leave year, given
     all at once or month by month, or unlimited (no balance is kept). -->
<template>
  <div class="allowance">
    <AppPillToggle v-model="mode" :options="MODES" aria-label="Allowance" />
    <template v-if="mode === 'fixed'">
      <v-text-field
        v-model.number="days"
        label="Days per leave year"
        type="number"
        min="0"
        max="365"
        step="0.5"
        suffix="days"
        class="days"
        v-bind="FIELD_PROPS"
      />
      <p class="text-caption text-medium-emphasis">
        New joiners get a share of this, set in Rules → New joiners.
      </p>
      <div class="given">
        <span class="text-body-2 font-weight-medium">Given</span>
        <AppPillToggle v-model="accrual" :options="ACCRUALS" aria-label="Given" />
      </div>
      <p class="text-caption text-medium-emphasis">
        {{ accrual === 'monthly' ? 'An equal part on the 1st of each month: 18 a year is 1.5 a month.' : 'The whole allowance is there from the first day of the leave year.' }}
      </p>
      <LeaveSwitchRow
        v-model="stops"
        class="stops"
        label="Stop requests past the balance"
        :description="stops ? 'People are told what\'s left and asked to use another type for the rest.' : 'Days past the balance are allowed and become loss of pay.'"
      />
    </template>
    <p v-else class="text-caption text-medium-emphasis">
      No balance is tracked. Requests still need approval.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import LeaveSwitchRow from '@/components/leave/settings/LeaveSwitchRow.vue'
import type { LeaveAccrual } from '@/types/leave'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

type Mode = 'fixed' | 'unlimited'

const unlimited = defineModel<boolean>('unlimited', { required: true })
const days = defineModel<number | null>('days', { required: true })
const accrual = defineModel<LeaveAccrual>('accrual', { required: true })
const stops = defineModel<boolean>('stops', { required: true })

const MODES: { label: string; value: Mode }[] = [
  { label: 'Fixed', value: 'fixed' },
  { label: 'Unlimited', value: 'unlimited' },
]

const ACCRUALS: { label: string; value: LeaveAccrual }[] = [
  { label: 'All at once', value: 'upfront' },
  { label: 'Monthly', value: 'monthly' },
]

const mode = computed<Mode>({
  get: () => (unlimited.value ? 'unlimited' : 'fixed'),
  set: value => {
    unlimited.value = value === 'unlimited'
  },
})
</script>

<style scoped>
.allowance {
  display: flex;
  flex-direction: column;
  align-items: flex-start; /* the toggle and field keep their own width */
  gap: 12px;
}
.days {
  width: 200px;
  flex: none;
}
.stops {
  align-self: stretch;
}
.given {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
