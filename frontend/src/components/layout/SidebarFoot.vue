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

<!-- Bottom of the sidebar: the theme switch and, on wide screens, the
     collapse / expand toggle. One row in every state, so the rows above
     it don't move when a rail opens under the pointer. -->
<template>
  <div class="sidebar-foot">
    <ThemeToggleButton :size="canRail ? 'small' : 'default'" />
    <v-btn
      v-if="canRail"
      :icon="rail ? 'mdi-chevron-right' : 'mdi-chevron-left'"
      variant="text"
      size="small"
      density="comfortable"
      :aria-label="toggleLabel"
      :title="toggleLabel"
      @click="emit('toggle-rail')"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ThemeToggleButton from './ThemeToggleButton.vue'

const props = defineProps<{
  /** The rail preference, which the toggle flips. */
  rail: boolean
  /** False on phones, where the sidebar is an overlay with no rail. */
  canRail: boolean
}>()
const emit = defineEmits<{ 'toggle-rail': [] }>()

const toggleLabel = computed(() => (props.rail ? 'Expand sidebar' : 'Collapse sidebar'))
</script>

<style scoped>
.sidebar-foot {
  /* Same spacing in every state: both buttons stay where the pointer
     found them when a rail opens under it. */
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
}
</style>
