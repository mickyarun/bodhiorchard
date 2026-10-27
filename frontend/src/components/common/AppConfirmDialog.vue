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

<!-- A short "are you sure?" dialog: a title, one paragraph and the
     confirming action. The default slot can add content (a note field, an
     error callout) under the paragraph.

       <AppConfirmDialog v-model="open" title="Close this bug?" body="…" action="Close bug" @confirm="close" />

     It stays open while ``busy``; the parent closes it once the action
     has succeeded. -->
<template>
  <v-dialog :model-value="modelValue" max-width="460" :persistent="busy" @update:model-value="emit('update:modelValue', $event)">
    <v-card color="surface" class="app-confirm">
      <h2 class="app-confirm__title">{{ title }}</h2>
      <p class="app-confirm__body"><slot name="body">{{ body }}</slot></p>
      <slot />
      <div class="app-confirm__actions">
        <v-btn variant="text" :disabled="busy" @click="emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="busy" @click="emit('confirm')">{{ action }}</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ modelValue: boolean; title: string; body?: string; action: string; busy?: boolean }>(), {
  body: '',
  busy: false,
})
const emit = defineEmits<{ 'update:modelValue': [open: boolean]; confirm: [] }>()
</script>

<style scoped>
.app-confirm {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 24px;
}
.app-confirm__title {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}
.app-confirm__body {
  margin: 0;
  font-size: 14px;
  line-height: 21px;
  color: rgb(var(--v-theme-ink-2));
}
.app-confirm__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
