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

<!-- One year's holidays: date, name, where it came from, and whether it's
     off for everyone (mandatory) or picked (optional). -->
<template>
  <ul class="holidays" aria-label="Holidays">
    <li v-for="holiday in holidays" :key="holiday.id" class="holiday">
      <span class="holiday__date text-body-2">{{ formatDayRange(holiday.date, holiday.date) }}</span>
      <span class="holiday__name text-body-2 font-weight-medium text-truncate">{{ holiday.name }}</span>
      <v-chip size="x-small" variant="tonal" label class="holiday__source">
        {{ HOLIDAY_SOURCE_LABELS[holiday.source] }}
      </v-chip>
      <AppPillToggle
        :model-value="holiday.kind"
        :options="HOLIDAY_KIND_OPTIONS"
        size="sm"
        :aria-label="`${holiday.name}: mandatory or optional`"
        @update:model-value="kind => emit('set-kind', holiday, kind)"
      />
      <v-btn
        icon="mdi-delete-outline"
        variant="text"
        size="small"
        :aria-label="`Delete ${holiday.name}`"
        @click="emit('remove', holiday.id)"
      />
    </li>
  </ul>
</template>

<script setup lang="ts">
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import type { HolidayKind } from '@/types/leave'
import type { HolidayAdminRead } from '@/types/leavePolicy'
import { formatDayRange } from '@/utils/leaveDates'
import { HOLIDAY_KIND_OPTIONS } from '@/utils/leavePolicy'
import { HOLIDAY_SOURCE_LABELS } from '@/utils/leavePolicyDisplay'

defineProps<{ holidays: HolidayAdminRead[] }>()
const emit = defineEmits<{
  'set-kind': [holiday: HolidayAdminRead, kind: HolidayKind]
  remove: [id: string]
}>()
</script>

<style scoped>
.holidays {
  list-style: none;
  padding: 0;
  margin: 0;
}
.holiday {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr) auto auto auto;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.holiday__date {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
@media (max-width: 600px) {
  .holiday {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .holiday__source {
    display: none;
  }
}
</style>
