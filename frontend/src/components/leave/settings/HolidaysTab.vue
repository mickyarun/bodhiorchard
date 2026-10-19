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
  <section>
    <div class="d-flex align-center justify-space-between flex-wrap ga-3 mb-3">
      <AppPillToggle v-model="year" :options="yearOptions" size="sm" />
      <v-btn
        variant="tonal"
        size="small"
        prepend-icon="mdi-download-outline"
        :loading="importing"
        :disabled="!policy.country_code"
        :title="policy.country_code ? '' : 'Set a country on the General tab first.'"
        @click="runImport"
      >
        Import public holidays
      </v-btn>
    </div>
    <AppCallout v-if="importResult" variant="success" class="mb-3">{{ importResult }}</AppCallout>
    <AppCallout v-if="store.holidaysError || rowError" variant="error" class="mb-3">
      {{ rowError || store.holidaysError }}
    </AppCallout>
    <v-progress-linear v-if="store.loading" indeterminate color="primary" />
    <p v-if="!store.loading && !store.holidays.length" class="text-body-2 text-medium-emphasis mb-3">
      No holidays for {{ year }} yet. Import your country's public holidays or add them below.
    </p>
    <div v-for="holiday in store.holidays" :key="holiday.id" class="holiday-row">
      <span class="text-body-2">{{ formatDayRange(holiday.date, holiday.date) }}</span>
      <span class="text-body-2 font-weight-medium text-truncate">{{ holiday.name }}</span>
      <AppPillToggle
        :model-value="holiday.kind"
        :options="HOLIDAY_KIND_OPTIONS"
        size="sm"
        @update:model-value="kind => setKind(holiday, kind)"
      />
      <v-btn icon="mdi-delete-outline" variant="text" size="small" :aria-label="`Delete ${holiday.name}`" @click="remove(holiday.id)" />
    </div>
    <HolidayAddRow :policy-id="policy.id" :year="year" class="mt-4" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import HolidayAddRow from '@/components/leave/settings/HolidayAddRow.vue'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import type { HolidayKind } from '@/types/leave'
import type { HolidayAdminRead, PolicyRead } from '@/types/leavePolicy'
import { formatDayRange } from '@/utils/leaveDates'
import { HOLIDAY_KIND_OPTIONS } from '@/utils/leavePolicy'

const props = defineProps<{ policy: PolicyRead }>()

const store = useLeavePolicyConfigStore()
const thisYear = new Date().getFullYear()
const year = ref(thisYear)
const yearOptions = [thisYear, thisYear + 1].map(value => ({ label: String(value), value }))
const importing = ref(false)
const importResult = ref('')
const rowError = ref('')

const key = computed(() => `${props.policy.id}:${year.value}`)
watch(
  key,
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

<style scoped>
.holiday-row {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
@media (max-width: 600px) {
  .holiday-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }
}
</style>
