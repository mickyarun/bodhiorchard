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

<template>
  <v-card
    class="tree-tooltip"
    :style="{ left: position.x + 'px', top: position.y + 'px' }"
    elevation="8"
    max-width="240"
  >
    <v-card-text class="pa-3">
      <div v-for="(value, key) in data" :key="String(key)" class="text-body-2">
        <span class="font-weight-medium text-medium-emphasis">{{ key }}:</span>
        {{ value }}
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
defineProps<{
  data: Record<string, unknown>
  position: { x: number; y: number }
}>()

defineEmits<{
  close: []
}>()
</script>

<style scoped>
.tree-tooltip {
  position: absolute;
  z-index: 100;
  pointer-events: none;
}
</style>
