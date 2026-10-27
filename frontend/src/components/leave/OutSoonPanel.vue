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

<!-- My leave sidebar: other people out in the next seven days. Says leave or
     WFH, never the leave type. -->
<template>
  <AppPanel title="Out this week">
    <template #action><router-link :to="{ name: 'leave-team' }">Calendar</router-link></template>
    <p v-if="out.error.value" class="out__empty">{{ out.error.value }}</p>
    <ul v-else-if="out.rows.value.length" class="out">
      <li v-for="row in out.rows.value" :key="row.id" class="out__row">
        <v-avatar size="30" color="brand" variant="tonal" class="out__avatar" aria-hidden="true">
          {{ initialsOf(row.name) }}
        </v-avatar>
        <span class="out__text">
          <span class="out__name">{{ row.name }}</span>
          <span class="out__when">{{ formatDayRange(row.start, row.end) }}</span>
        </span>
        <span class="out__label">{{ row.label }}<template v-if="row.pending">, pending</template></span>
      </li>
    </ul>
    <p v-else-if="!out.loading.value" class="out__empty">Nobody else is out this week.</p>
  </AppPanel>
</template>

<script setup lang="ts">
import AppPanel from '@/components/common/AppPanel.vue'
import { useOutSoon } from '@/composables/useOutSoon'
import { initialsOf } from '@/utils/avatar'
import { formatDayRange } from '@/utils/leaveDates'

const WINDOW_DAYS = 7
const LIMIT = 5

const out = useOutSoon(WINDOW_DAYS, LIMIT)
</script>

<style scoped>
.out {
  list-style: none;
  margin: 0;
  padding: 0;
}
.out__row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
}
.out__avatar {
  font-size: 11px;
  font-weight: 600;
}
.out__text {
  display: flex;
  flex-direction: column;
  flex-grow: 1;
  min-width: 0;
}
.out__name {
  font-size: var(--text-sm);
  font-weight: 500;
}
.out__when,
.out__label {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.out__label {
  color: rgb(var(--v-theme-ink-2));
  white-space: nowrap;
}
.out__empty {
  margin: 0;
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
