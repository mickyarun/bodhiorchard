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

<!-- Working days, Monday to Sunday (0–6). At least one stays selected. -->
<template>
  <div>
    <div class="text-caption text-medium-emphasis mb-1">Working days</div>
    <v-chip-group
      :model-value="modelValue"
      multiple
      mandatory
      selected-class="text-primary"
      :disabled="disabled"
      @update:model-value="update"
    >
      <v-chip v-for="(label, index) in WEEKDAY_SHORT" :key="label" :value="index" filter variant="outlined" size="small">
        {{ label }}
      </v-chip>
    </v-chip-group>
  </div>
</template>

<script setup lang="ts">
import { WEEKDAY_SHORT } from '@/utils/leaveDates'

defineProps<{ modelValue: number[]; disabled?: boolean }>()
const emit = defineEmits<(e: 'update:modelValue', value: number[]) => void>()

function update(value: unknown): void {
  const days = Array.isArray(value) ? value.filter((d): d is number => typeof d === 'number') : []
  emit('update:modelValue', [...days].sort((a, b) => a - b))
}
</script>
