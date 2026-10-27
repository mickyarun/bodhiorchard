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

<!-- Department filter as a row of pill buttons with a head count each.
     "All" clears the filter; picking the selected department again does too. -->
<template>
  <div class="dept-chips" role="group" aria-label="Department">
    <button
      v-for="chip in chips"
      :key="chip.name"
      type="button"
      class="dept-chips__chip"
      :class="{ 'dept-chips__chip--on': chip.value === model }"
      :aria-pressed="chip.value === model"
      @click="model = chip.value === model ? null : chip.value"
    >
      {{ chip.name }} <span class="dept-chips__count">{{ chip.count }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DepartmentCount } from '@/utils/employeeDirectory'

const props = defineProps<{ departments: DepartmentCount[]; total: number }>()
const model = defineModel<string | null>({ required: true })

const chips = computed(() => [
  { name: 'All', value: null, count: props.total },
  ...props.departments.map(d => ({ name: d.name, value: d.name, count: d.count })),
])
</script>

<style scoped>
.dept-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}
.dept-chips__chip {
  height: 34px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-ink-2));
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  transition: background-color var(--dur-short) ease;
}
.dept-chips__chip:hover:not(.dept-chips__chip--on) {
  background: rgb(var(--v-theme-surface-variant));
}
.dept-chips__chip:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}
.dept-chips__count {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.dept-chips__chip--on {
  background: var(--color-accent-soft);
  border-color: rgb(var(--v-theme-primary));
  color: var(--color-accent-text);
}
.dept-chips__chip--on .dept-chips__count {
  color: inherit;
}
</style>
