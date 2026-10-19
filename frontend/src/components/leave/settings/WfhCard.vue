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

<!-- Rules → Work from home: how WFH requests are approved. -->
<template>
  <LeaveSectionCard
    icon="mdi-home-account"
    title="Work from home"
    caption="Work from home doesn't use any leave allowance."
  >
    <LeaveFormGrid>
      <!-- The options are full sentences: give them the whole row. -->
      <v-select v-model="approval" :items="MODES" label="Approval" class="span-2" v-bind="FIELD_PROPS" />
      <v-text-field
        v-if="approval === 'auto_within_allowance'"
        v-model.number="monthlyAutoDays"
        label="Automatic days a month"
        type="number"
        min="0"
        max="31"
        suffix="days"
        hint="Requests past this go to the approver."
        persistent-hint
        v-bind="FIELD_PROPS"
      />
    </LeaveFormGrid>
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import LeaveFormGrid from '@/components/leave/settings/LeaveFormGrid.vue'
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import type { WfhApproval } from '@/types/leave'
import { selectItems } from '@/utils/employee'
import { WFH_APPROVAL_LABELS } from '@/utils/leave'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const approval = defineModel<WfhApproval>('approval', { required: true })
const monthlyAutoDays = defineModel<number>('monthlyAutoDays', { required: true })

const MODES = selectItems<WfhApproval>(WFH_APPROVAL_LABELS)
</script>
