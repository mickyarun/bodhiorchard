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

<!-- A labelled dropdown filter button: "Assignee" until something is
     picked, then "Assignee: Meera Iyer". The first item clears it. -->
<template>
  <v-menu v-model="menuOpen" location="bottom start">
    <template #activator="{ props: menuProps }">
      <v-btn
        ref="trigger"
        v-bind="menuProps"
        variant="outlined"
        class="board-filter"
        :class="{ 'board-filter--set': selected }"
        append-icon="mdi-chevron-down"
        aria-haspopup="listbox"
      >
        <span class="board-filter__text">
          {{ label }}<template v-if="selected">: {{ selected.label }}</template>
        </span>
      </v-btn>
    </template>
    <v-list density="compact" min-width="200" max-height="320" role="listbox" :aria-label="label">
      <v-list-item role="option" :active="model === null" :aria-selected="model === null" @click="pick(null)">
        <v-list-item-title>{{ allLabel }}</v-list-item-title>
      </v-list-item>
      <v-list-item
        v-for="opt in options"
        :key="opt.value"
        role="option"
        :active="opt.value === model"
        :aria-selected="opt.value === model"
        @click="pick(opt.value)"
      >
        <v-list-item-title>{{ opt.label }}</v-list-item-title>
      </v-list-item>
    </v-list>
  </v-menu>
</template>

<script setup lang="ts" generic="V extends string">
import { computed, nextTick, ref } from 'vue'
import type { FilterOption } from '@/utils/budBoard'

const props = defineProps<{
  label: string
  allLabel: string
  options: FilterOption<V>[]
}>()

const model = defineModel<V | null>({ required: true })
const menuOpen = ref(false)
const trigger = ref<{ $el: HTMLElement } | null>(null)
const selected = computed(() => props.options.find(o => o.value === model.value) ?? null)

// Picking closes the menu and puts focus back on the filter button, so
// keyboard users carry on from where they were.
async function pick(value: V | null): Promise<void> {
  model.value = value
  menuOpen.value = false
  await nextTick()
  trigger.value?.$el.focus()
}
</script>

<style scoped>
.board-filter {
  height: 38px;
  padding: 0 10px 0 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-ink-2));
  border-color: rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-surface));
}
.board-filter--set {
  color: var(--color-accent-text);
  border-color: rgba(var(--v-theme-primary), 0.5);
}
.board-filter__text {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
