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

<!-- A labelled radio group drawn as tiles: icon, title, optional badge
     and a one-line description per option. -->
<template>
  <div class="tiles-wrap">
    <div :id="labelId" class="tiles-label">{{ label }}</div>
    <div role="radiogroup" :aria-labelledby="labelId" class="tiles">
      <button
        v-for="opt in options"
        :key="opt.value"
        type="button"
        role="radio"
        :aria-checked="modelValue === opt.value"
        class="tile"
        :class="{ 'tile--on': modelValue === opt.value }"
        @click="emit('update:modelValue', opt.value)"
      >
        <v-icon :icon="modelValue === opt.value ? 'mdi-radiobox-marked' : 'mdi-radiobox-blank'" size="20" class="tile__radio" />
        <span class="tile__body">
          <span class="tile__head">
            <v-icon :icon="opt.icon" size="18" class="tile__icon" />
            <span class="tile__title">{{ opt.title }}</span>
            <AppTag v-if="opt.badge">{{ opt.badge }}</AppTag>
          </span>
          <span class="tile__desc">{{ opt.description }}</span>
        </span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useId } from 'vue'
import AppTag from '@/components/common/AppTag.vue'
import type { ChoiceTile } from '@/utils/aiProviderOptions'

defineProps<{ modelValue: string; options: ChoiceTile[]; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [string] }>()
const labelId = useId()
</script>

<style scoped>
.tiles-label {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  gap: 10px;
}
.tile {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 12px 14px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
  background: rgb(var(--v-theme-surface));
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color var(--dur-short) ease, background-color var(--dur-short) ease;
}
.tile:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
}
.tile:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}
.tile--on {
  border-color: rgb(var(--v-theme-primary));
  background: var(--color-accent-soft);
}
.tile__radio {
  color: rgb(var(--v-theme-on-surface-variant));
}
.tile--on .tile__radio {
  color: rgb(var(--v-theme-primary));
}
.tile__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.tile__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.tile__icon {
  color: rgb(var(--v-theme-ink-2));
}
.tile__title {
  font-size: 14px;
  font-weight: 500;
}
.tile__desc {
  font-size: 12px;
  line-height: 1.5;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
