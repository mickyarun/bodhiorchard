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

<!-- A policy's holiday calendar for this year or next. Mandatory
     holidays are off for everyone; optional ones are picked. -->
<template>
  <LeaveSectionCard
    icon="mdi-calendar-star"
    title="Holidays"
    caption="Days off for everyone on this policy. Leave isn't counted on them."
  >
    <template #actions>
      <v-btn variant="tonal" prepend-icon="mdi-plus" :disabled="adding" @click="adding = true">Add holiday</v-btn>
      <v-btn
        variant="tonal"
        prepend-icon="mdi-download-outline"
        :loading="importing"
        :disabled="!policy.country_code"
        @click="runImport"
      >
        Import public holidays
      </v-btn>
    </template>

    <div class="d-flex align-center flex-wrap ga-3 mb-4">
      <AppPillToggle v-model="year" :options="yearOptions" size="sm" aria-label="Year" />
      <span class="text-body-2 text-medium-emphasis" aria-live="polite">{{ year }} · {{ summary }}</span>
    </div>
    <AppCallout v-if="!policy.country_code" variant="info" class="mb-4">
      Set a country in <strong>Edit details</strong> to import public holidays.
      <template #actions>
        <v-btn size="small" variant="text" @click="emit('edit-details')">Edit details</v-btn>
      </template>
    </AppCallout>
    <AppCallout v-if="importResult" variant="success" class="mb-4">{{ importResult }}</AppCallout>
    <AppCallout v-if="store.holidaysError || rowError" variant="error" class="mb-4">
      {{ rowError || store.holidaysError }}
    </AppCallout>
    <HolidayAddRow v-if="adding" :policy-id="policy.id" :year="year" class="mb-4" @close="adding = false" />
    <v-progress-linear v-if="store.loading" indeterminate color="primary" />
    <LeaveEmptyState
      v-else-if="!store.holidays.length && !adding"
      icon="mdi-calendar-blank-outline"
      :title="`No holidays for ${year} yet`"
      body="Import your country's public holidays, or add your own."
    >
      <template #actions>
        <v-btn variant="flat" color="primary" prepend-icon="mdi-plus" @click="adding = true">Add holiday</v-btn>
      </template>
    </LeaveEmptyState>
    <HolidayList v-else :holidays="store.holidays" @set-kind="setKind" @remove="remove" />
  </LeaveSectionCard>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import HolidayAddRow from '@/components/leave/settings/HolidayAddRow.vue'
import HolidayList from '@/components/leave/settings/HolidayList.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import LeaveSectionCard from '@/components/leave/settings/LeaveSectionCard.vue'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import type { HolidayKind } from '@/types/leave'
import type { HolidayAdminRead, PolicyRead } from '@/types/leavePolicy'
import { holidaySummary } from '@/utils/leavePolicyDisplay'

const props = defineProps<{ policy: PolicyRead }>()
const emit = defineEmits<{ 'edit-details': [] }>()

const store = useLeavePolicyConfigStore()
const thisYear = new Date().getFullYear()
const year = ref(thisYear)
const yearOptions = [thisYear, thisYear + 1].map(value => ({ label: String(value), value }))
const adding = ref(false)
const importing = ref(false)
const importResult = ref('')
const rowError = ref('')
const summary = computed(() => holidaySummary(store.holidays))

watch(
  () => `${props.policy.id}:${year.value}`,
  () => {
    importResult.value = ''
    rowError.value = ''
    void store.fetchHolidays(props.policy.id, year.value)
  },
  { immediate: true },
)

async function runImport(): Promise<void> {
  importing.value = true
  rowError.value = ''
  const result = await store.importHolidays(props.policy.id, year.value)
  importing.value = false
  if (typeof result === 'string') {
    rowError.value = result
    importResult.value = ''
    return
  }
  importResult.value = `Added ${result.added}, skipped ${result.skipped} already on the calendar.`
}

async function setKind(holiday: HolidayAdminRead, kind: HolidayKind): Promise<void> {
  rowError.value =
    (await store.updateHoliday(holiday, { date: holiday.date, name: holiday.name, kind })) ?? ''
}

async function remove(id: string): Promise<void> {
  rowError.value = (await store.deleteHoliday(id)) ?? ''
}
</script>
