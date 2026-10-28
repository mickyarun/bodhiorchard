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

<!-- Import bar — accepts a .md file with YAML frontmatter and hands its text
     to the dialog, which splits it across the right fields, so pasting an
     off-the-shelf skill from the Claude Code catalog "just works". -->
<template>
  <div class="import-row">
    <div class="import-text">
      <v-icon icon="mdi-import" size="14" class="mr-1" />
      Import an existing skill file
    </div>
    <v-btn
      variant="tonal"
      color="primary"
      size="small"
      class="text-none"
      prepend-icon="mdi-upload-outline"
      @click="triggerImport"
    >
      Choose .md
    </v-btn>
    <input
      ref="fileInputEl"
      type="file"
      accept=".md,text/markdown,text/plain"
      class="hidden-file"
      @change="onFileSelected"
    >
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  loaded: [text: string]
  failed: [message: string]
}>()

const fileInputEl = ref<HTMLInputElement | null>(null)

function triggerImport(): void {
  fileInputEl.value?.click()
}

async function onFileSelected(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  // Reset the input so re-selecting the same file still fires @change.
  target.value = ''
  if (!file) return
  try {
    emit('loaded', await file.text())
  } catch (err) {
    emit('failed', err instanceof Error ? err.message : 'Failed to read file')
  }
}
</script>

<style scoped>
.import-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 14px;
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.18);
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.import-text {
  flex: 1;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  display: flex;
  align-items: center;
}

.hidden-file {
  position: absolute;
  width: 0;
  height: 0;
  opacity: 0;
  pointer-events: none;
}
</style>
