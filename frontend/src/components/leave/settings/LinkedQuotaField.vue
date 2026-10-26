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

<!-- A library type's yearly quota on one policy: the library's default, or
     the policy's own (a number of days, or unlimited). -->
<template>
  <div class="linked-quota">
    <AppPillToggle v-model="choice" :options="options" aria-label="Yearly quota" />
    <v-text-field
      v-if="choice === 'fixed'"
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
    <p class="text-caption text-medium-emphasis">{{ caption }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import type { Decimalish } from '@/types/leave'
import { type QuotaChoice, quotaLabel } from '@/utils/leaveLibrary'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const props = defineProps<{
  /** The library default; undefined while it loads. */
  libraryQuota: Decimalish | null | undefined
  /** A type that approves itself always needs a quota, so "Unlimited" isn't offered. */
  autoApprove: boolean
}>()
const choice = defineModel<QuotaChoice>('choice', { required: true })
const days = defineModel<number | null>('days', { required: true })

const options = computed(() => {
  const all: { label: string; value: QuotaChoice }[] = [
    {
      label: props.libraryQuota === undefined ? 'Library' : `Library (${quotaLabel(props.libraryQuota)})`,
      value: 'library',
    },
    { label: 'Own number', value: 'fixed' },
    { label: 'Unlimited', value: 'unlimited' },
  ]
  return props.autoApprove ? all.filter(o => o.value !== 'unlimited') : all
})

const caption = computed(() => {
  switch (choice.value) {
    case 'library':
      return 'Follows the library: a change to its quota there changes it here too.'
    case 'fixed':
      return "This policy's own quota; library changes to the quota don't touch it."
    default:
      return 'No balance is tracked on this policy. Requests still need approval.'
  }
})
</script>

<style scoped>
.linked-quota {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}
.days {
  width: 200px;
  flex: none;
}
</style>
