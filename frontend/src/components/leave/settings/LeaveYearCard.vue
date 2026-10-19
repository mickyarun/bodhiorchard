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

<!-- Rules → Leave year: when it starts, how far back people can request,
     and optional holidays. The start is locked once requests exist, so
     past balances stay valid. -->
<template>
  <LeaveSectionCard
    icon="mdi-calendar-sync-outline"
    title="Leave year"
    caption="Allowances reset at the start of each leave year."
  >
    <AppCallout v-if="locked" variant="warning" class="mb-5">
      The start month is locked: people have already requested leave on this policy, and every
      balance would shift if it moved.
    </AppCallout>
    <LeaveFormGrid>
      <v-select
        v-model="startMonth"
        :items="MONTH_ITEMS"
        label="Leave year starts in"
        :disabled="locked"
        v-bind="FIELD_PROPS"
      />
      <v-text-field
        v-model.number="backdateDays"
        label="Backdate limit"
        type="number"
        min="0"
        max="365"
        suffix="days"
        hint="How far back someone can request leave."
        persistent-hint
        v-bind="FIELD_PROPS"
      />
      <v-text-field
        v-model.number="optionalHolidays"
        label="Optional holidays a year"
        type="number"
        min="0"
        max="60"
        hint="How many optional holidays each person can pick."
        persistent-hint
        v-bind="FIELD_PROPS"
      />
    </LeaveFormGrid>
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveFormGrid from '@/components/leave/settings/LeaveFormGrid.vue'
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import { MONTH_ITEMS } from '@/utils/leavePolicy'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

defineProps<{ locked: boolean }>()
const startMonth = defineModel<number>('startMonth', { required: true })
const backdateDays = defineModel<number>('backdateDays', { required: true })
const optionalHolidays = defineModel<number>('optionalHolidays', { required: true })
</script>
