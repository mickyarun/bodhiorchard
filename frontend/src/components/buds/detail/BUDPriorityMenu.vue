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

<!-- The BUD's priority tag. With edit rights it opens a P0–P3 menu;
     otherwise it's a plain tag. -->
<template>
  <v-menu v-if="editable" location="bottom start">
    <template #activator="{ props: menuProps }">
      <button
        v-bind="menuProps"
        type="button"
        class="priority-menu__btn"
        :aria-label="`Priority ${priority}. Change priority`"
      >
        <BudPriorityChip :priority="priority" />
        <v-icon icon="mdi-chevron-down" size="14" />
      </button>
    </template>
    <!-- A menu of radio items: the button says it opens a menu, and the
         current priority is the checked one. -->
    <v-list density="compact" min-width="120" role="menu" aria-label="Priority">
      <v-list-item
        v-for="p in BUD_PRIORITIES"
        :key="p"
        role="menuitemradio"
        :aria-checked="priority === p"
        :active="priority === p"
        @click="emit('change', p)"
      >
        <v-list-item-title>{{ p }}</v-list-item-title>
      </v-list-item>
    </v-list>
  </v-menu>
  <BudPriorityChip v-else :priority="priority" />
</template>

<script setup lang="ts">
import BudPriorityChip from '@/components/buds/BudPriorityChip.vue'
import { BUD_PRIORITIES, type BUDPriority } from '@/types'

defineProps<{ priority: BUDPriority; editable: boolean }>()
const emit = defineEmits<{ change: [priority: BUDPriority] }>()
</script>

<style scoped>
.priority-menu__btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 0;
  border: 0;
  background: transparent;
  color: rgb(var(--v-theme-on-surface-variant));
  cursor: pointer;
  border-radius: 6px;
}
.priority-menu__btn:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}
</style>
