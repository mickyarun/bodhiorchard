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

<!-- Dates for leave reports and the approvals filter: a preset, or a custom
     From / To. `any` (approvals only) means no date filter. -->
<template>
  <div class="d-flex flex-wrap align-center ga-3">
    <v-select
      :model-value="preset"
      :items="items"
      label="Dates"
      density="compact"
      variant="outlined"
      hide-details
      class="preset"
      @update:model-value="choose"
    />
    <template v-if="preset === 'custom'">
      <v-text-field
        :model-value="start"
        type="date"
        label="From"
        density="compact"
        variant="outlined"
        hide-details
        @update:model-value="(v: string) => emit('update:start', v)"
      />
      <v-text-field
        :model-value="end"
        type="date"
        label="To"
        density="compact"
        variant="outlined"
        hide-details
        @update:model-value="(v: string) => emit('update:end', v)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { presetRange, RANGE_LABELS, type RangePreset } from '@/utils/leaveRanges'

export type DatePreset = RangePreset | 'any'

const props = defineProps<{
  preset: DatePreset
  start: string
  end: string
  presets: DatePreset[]
}>()
const emit = defineEmits<{
  'update:preset': [DatePreset]
  'update:start': [string]
  'update:end': [string]
}>()

const items = computed(() =>
  props.presets.map(value => ({ value, title: value === 'any' ? 'Any dates' : RANGE_LABELS[value] })),
)

function choose(next: DatePreset): void {
  emit('update:preset', next)
  if (next === 'any') {
    emit('update:start', '')
    emit('update:end', '')
    return
  }
  const range = presetRange(next, new Date(), props.start ? { start: props.start, end: props.end } : undefined)
  emit('update:start', range.start)
  emit('update:end', range.end)
}
</script>

<style scoped>
.preset {
  min-width: 170px;
  max-width: 200px;
}
</style>
