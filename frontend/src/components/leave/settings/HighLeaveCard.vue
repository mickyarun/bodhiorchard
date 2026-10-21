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
<!-- Rules → High-leave warning: for unlimited leave, a heads-up and then a
     warning once someone has taken this many days in the leave year. Shown
     to them when requesting, to approvers, and in reports. Empty = off. -->
<template>
  <LeaveSectionCard
    icon="mdi-alert-circle-outline"
    title="High-leave warning"
    caption="For unlimited leave: flag people who've taken a lot this year. Leave types can opt out (e.g. sick)."
  >
    <LeaveFormGrid>
      <v-text-field
        v-model="notice"
        label="Heads-up after"
        type="number"
        min="1"
        max="365"
        suffix="days"
        hint="A gentle note. Leave empty for none."
        persistent-hint
        v-bind="FIELD_PROPS"
      />
      <v-text-field
        v-model="warning"
        label="Warning after"
        type="number"
        min="1"
        max="365"
        suffix="days"
        hint="&quot;Too many leaves&quot;. Leave empty for none."
        persistent-hint
        v-bind="FIELD_PROPS"
      />
    </LeaveFormGrid>
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LeaveFormGrid from '@/components/leave/settings/LeaveFormGrid.vue'
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const noticeDays = defineModel<number | null>('noticeDays', { required: true })
const warningDays = defineModel<number | null>('warningDays', { required: true })

/** A number field gives a string; an empty one means "off" (null). */
function daysField(model: typeof noticeDays) {
  return computed<string>({
    get: () => (model.value === null ? '' : String(model.value)),
    set: value => {
      model.value = value === '' || value === null ? null : Number(value)
    },
  })
}

const notice = daysField(noticeDays)
const warning = daysField(warningDays)
</script>
