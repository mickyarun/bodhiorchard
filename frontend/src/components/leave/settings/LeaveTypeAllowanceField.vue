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

<!-- A leave type's allowance: a fixed number of days each leave year, or
     unlimited (no balance is kept). -->
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
    </template>
    <p v-else class="text-caption text-medium-emphasis">
      No balance is tracked. Requests still need approval.
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

type Mode = 'fixed' | 'unlimited'

const unlimited = defineModel<boolean>('unlimited', { required: true })
const days = defineModel<number | null>('days', { required: true })

const MODES: { label: string; value: Mode }[] = [
  { label: 'Fixed', value: 'fixed' },
  { label: 'Unlimited', value: 'unlimited' },
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
</style>
