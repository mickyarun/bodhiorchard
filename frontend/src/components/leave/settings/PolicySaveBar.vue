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

<!-- Sticky bar under a form with unsaved changes: discard or save them. -->
<template>
  <v-slide-y-reverse-transition>
    <div v-if="visible" class="save-bar" role="region" aria-label="Unsaved changes">
      <v-icon icon="mdi-circle-medium" color="warning" aria-hidden="true" />
      <span class="text-body-2 font-weight-medium">Unsaved changes</span>
      <v-spacer />
      <v-btn variant="text" :disabled="saving" @click="emit('discard')">Discard</v-btn>
      <v-btn color="primary" variant="flat" :loading="saving" @click="emit('save')">Save changes</v-btn>
    </div>
  </v-slide-y-reverse-transition>
</template>

<script setup lang="ts">
defineProps<{ visible: boolean; saving: boolean }>()
const emit = defineEmits<{ discard: []; save: [] }>()
</script>

<style scoped>
.save-bar {
  position: sticky;
  bottom: 16px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 10px 16px;
  border-radius: 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
}
</style>
