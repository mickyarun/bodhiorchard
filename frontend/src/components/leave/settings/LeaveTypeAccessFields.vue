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
      <AppPillToggle v-model="mode" :options="WHO" aria-label="Who can use it" />
    </div>
    <v-chip-group v-if="genders" v-model="genders" multiple column selected-class="text-primary" aria-label="Genders">
      <v-chip v-for="option in GENDERS" :key="option.value" :value="option.value" filter variant="outlined" size="small">
        {{ option.label }}
      </v-chip>
    </v-chip-group>
    <p class="text-caption text-medium-emphasis">
      {{ genders ? whoHint : 'Everyone on the policy.' }}
    </p>
    <LeaveSwitchRow
      v-model="autoApprove"
      :disabled="!canApprove"
      label="Approve automatically"
      :description="canApprove ? 'Approved as soon as it\'s sent, unless it would be unpaid. Managers get a heads-up.' : 'Only people who approve leave can switch this on.'"
    />
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
import { usePermissions } from '@/composables/usePermissions'
import type { Gender } from '@/types/employee'
import type { Decimalish } from '@/types/leave'
import { GENDER_LABELS } from '@/utils/employee'
import { toNumberOrNull } from '@/utils/leave'
import { FIELD_PROPS, gendersLabel } from '@/utils/leavePolicyDisplay'

type Who = 'everyone' | 'some'

const genders = defineModel<Gender[] | null>('genders', { required: true })
const autoApprove = defineModel<boolean>('autoApprove', { required: true })
const monthlyLimit = defineModel<Decimalish | null>('monthlyLimit', { required: true })

const { canApproveLeave: canApprove } = usePermissions()

const WHO: { label: string; value: Who }[] = [
  { label: 'Everyone', value: 'everyone' },
  { label: 'Some genders', value: 'some' },
]
const GENDERS = (Object.keys(GENDER_LABELS) as Gender[]).map(value => ({ value, label: GENDER_LABELS[value] }))

const mode = computed<Who>({
  get: () => (genders.value ? 'some' : 'everyone'),
  set: value => {
    genders.value = value === 'some' ? ['female'] : null
  },
})

const whoHint = computed(() =>
  genders.value?.length
    ? `Only people whose profile gender is ${gendersLabel(genders.value)} see it. Set gender on each person's Personal tab.`
    : 'Pick at least one.',
)

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
