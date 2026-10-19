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

<!-- Colour for a leave type on calendars, with a live preview of how its
     chip will look. -->
<template>
  <div class="d-flex align-center flex-wrap ga-4">
    <div class="swatches" role="radiogroup" aria-label="Colour">
      <button
        v-for="option in SWATCH_OPTIONS"
        :key="option.key"
        type="button"
        role="radio"
        class="swatch"
        :class="{ 'swatch--active': color === option.key }"
        :style="{ background: `rgb(var(--v-theme-${swatchColor(option.key)}))` }"
        :aria-checked="color === option.key"
        :aria-label="option.name"
        :title="option.name"
        @click="color = option.key"
      >
        <v-icon v-if="color === option.key" icon="mdi-check" size="16" color="white" />
      </button>
    </div>
    <v-chip :color="swatchColor(color)" variant="tonal" label aria-label="Preview">
      <span class="preview-dot" :style="{ background: `rgb(var(--v-theme-${swatchColor(color)}))` }" />
      {{ name.trim() || 'Leave type' }}
    </v-chip>
  </div>
</template>

<script setup lang="ts">
import { swatchColor } from '@/utils/leave'
import { SWATCH_OPTIONS } from '@/utils/leavePolicyDisplay'

defineProps<{ name: string }>()
const color = defineModel<string>({ required: true })
</script>

<style scoped>
.swatches {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.swatch {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
}
.swatch--active,
.swatch:focus-visible {
  outline: 2px solid rgb(var(--v-theme-on-surface));
  outline-offset: 2px;
}
.preview-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}
</style>
