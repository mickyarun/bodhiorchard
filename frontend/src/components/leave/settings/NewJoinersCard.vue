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

<!-- Rules → New joiners: how someone who joins (or moves onto this
     policy) mid-year is allocated leave. -->
<template>
  <LeaveSectionCard
    icon="mdi-account-plus-outline"
    title="New joiners"
    caption="Someone who joins, or moves onto this policy, after the leave year starts gets a share of each leave type's allowance. A year's allocation is fixed the first time they request leave in it, so changes here apply to people who haven't yet."
  >
    <LeaveFormGrid>
      <v-select v-model="method" :items="METHODS" label="Prorate" class="span-2" v-bind="FIELD_PROPS" />
      <v-text-field
        v-if="method === 'monthly'"
        v-model.number="cutoffDay"
        label="Joining month counts up to day"
        type="number"
        min="1"
        max="31"
        hint="E.g. 15: joining on the 15th counts that month, the 16th doesn't."
        persistent-hint
        v-bind="FIELD_PROPS"
      />
      <v-select
        v-if="method !== 'none'"
        v-model="rounding"
        :items="ROUNDINGS"
        label="Round the result"
        hint="Never rounds above the full allowance."
        persistent-hint
        v-bind="FIELD_PROPS"
      />
    </LeaveFormGrid>
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import LeaveFormGrid from '@/components/leave/settings/LeaveFormGrid.vue'
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import type { AllocationRounding, ProrationMethod } from '@/types/leavePolicy'
import { selectItems } from '@/utils/employee'
import { PRORATION_LABELS, ROUNDING_LABELS } from '@/utils/leavePolicy'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const method = defineModel<ProrationMethod>('method', { required: true })
const cutoffDay = defineModel<number>('cutoffDay', { required: true })
const rounding = defineModel<AllocationRounding>('rounding', { required: true })

const METHODS = selectItems<ProrationMethod>(PRORATION_LABELS)
const ROUNDINGS = selectItems<AllocationRounding>(ROUNDING_LABELS)
</script>
