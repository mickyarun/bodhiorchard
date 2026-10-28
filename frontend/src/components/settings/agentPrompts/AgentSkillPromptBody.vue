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

<!-- The skill prompt: a monospace textarea in edit mode, the sanitised
     rendered markdown in preview mode. -->
<template>
  <v-textarea
    v-if="mode === 'edit'"
    v-model="prompt"
    variant="outlined"
    density="compact"
    auto-grow
    :rows="14"
    class="prompt-editor"
    hide-details
  />
  <div
    v-else
    class="preview-content rendered-markdown"
    v-html="renderedPreview"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { PreviewMode } from './skillEditForm.util'

defineProps<{ mode: PreviewMode }>()
const prompt = defineModel<string>('prompt', { required: true })

const renderedPreview = computed(() => {
  if (!prompt.value) return ''
  const raw = marked.parse(prompt.value, { async: false }) as string
  return DOMPurify.sanitize(raw)
})
</script>

<style scoped>
.prompt-editor :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.65;
}

.prompt-editor :deep(.v-field) {
  background: rgb(var(--v-theme-background));
}

.preview-content {
  max-height: 540px;
  overflow-y: auto;
  padding: 16px 18px;
  background: rgb(var(--v-theme-background));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
  font-size: 13.5px;
  line-height: 1.7;
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.preview-content :deep(h1),
.preview-content :deep(h2),
.preview-content :deep(h3) { margin: 14px 0 6px; font-weight: 600; }
.preview-content :deep(h1) { font-size: 1.25em; }
.preview-content :deep(h2) { font-size: 1.1em; }
.preview-content :deep(h3) { font-size: 1em; }
.preview-content :deep(code) {
  background: rgba(var(--v-theme-on-surface), 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.87em;
}
.preview-content :deep(pre) {
  background: rgb(var(--v-theme-background));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 6px;
  padding: 12px 16px;
  margin: 10px 0;
  overflow-x: auto;
}
.preview-content :deep(pre code) { background: none; padding: 0; }
.preview-content :deep(ul),
.preview-content :deep(ol) { padding-left: 20px; margin: 8px 0; }
</style>
