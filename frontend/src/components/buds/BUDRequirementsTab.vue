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

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { BUDDocument } from '@/types'
import { renderMarkdown } from '@/utils/markdown'
import AppCallout from '@/components/common/AppCallout.vue'
import BUDLinkedFeaturesPanel from './BUDLinkedFeaturesPanel.vue'
import { pmUpdatePrompt } from '@/utils/budPromptTemplates'
import './bud-section.css'

const props = defineProps<{
  bud: BUDDocument
  editing: boolean
  editValue: string
  agentLocked: boolean
}>()

const emit = defineEmits<{
  'update:editValue': [value: string]
  save: []
  startEdit: []
  enrich: []
  'features-changed': []
}>()

const isJiraImported = computed(() => props.bud.metadata?.source === 'jira_import')

const showEnrichHint = computed(() =>
  isJiraImported.value
  && !props.agentLocked
  && (props.bud.requirements_md?.length ?? 0) < 200,
)

const copiedPrompt = ref(false)
const promptText = computed(() => pmUpdatePrompt(props.bud.bud_number, props.bud.id))

async function copyPrompt(): Promise<void> {
  try {
    await navigator.clipboard.writeText(promptText.value)
    copiedPrompt.value = true
    setTimeout(() => { copiedPrompt.value = false }, 2000)
  } catch {
    // Non-secure context — falls back to the selectable pre block.
  }
}
</script>

<template>
  <div class="bud-requirements-tab">
    <BUDLinkedFeaturesPanel
      v-if="bud.id"
      :bud-id="bud.id"
      class="mx-4 mt-3 mb-3"
      @change="emit('features-changed')"
    />
    <textarea
      v-if="editing"
      :value="editValue"
      class="section-editor"
      placeholder="Write requirements in markdown..."
      @input="emit('update:editValue', ($event.target as HTMLTextAreaElement).value)"
      @blur="emit('save')"
    />
    <template v-else-if="bud.requirements_md">
      <v-alert
        v-if="showEnrichHint"
        type="info"
        variant="tonal"
        density="compact"
        class="mx-4 mt-3 mb-0"
      >
        <div class="d-flex align-center ga-3">
          <div class="text-caption flex-grow-1">
            Imported from Jira — use AI to expand into a full PRD with acceptance criteria
          </div>
          <v-btn size="small" variant="flat" color="primary" @click="emit('enrich')">
            <v-icon start size="15">mdi-creation-outline</v-icon>
            Enrich
          </v-btn>
        </div>
      </v-alert>
      <div class="rendered-markdown" v-html="renderMarkdown(bud.requirements_md)" />
    </template>
    <!-- Empty state — prompt panel + generate button -->
    <div v-else class="phase-prompt-panel">
      <AppCallout
        variant="info"
        eyebrow="Write requirements"
        icon="mdi-text-box-outline"
        class="mb-4"
      >
        Paste the prompt into your local Claude Code to draft requirements
        via MCP, or use the AI button to let the in-app agent enrich them.
      </AppCallout>

      <div class="prompt-wrapper">
        <pre class="prompt-text">{{ promptText }}</pre>
        <v-btn
          variant="tonal"
          size="small"
          class="copy-btn"
          @click="copyPrompt"
        >
          <v-icon start size="15">
            {{ copiedPrompt ? 'mdi-check' : 'mdi-content-copy' }}
          </v-icon>
          {{ copiedPrompt ? 'Copied' : 'Copy prompt' }}
        </v-btn>
      </div>

      <div class="d-flex ga-2 mt-4">
        <v-btn
          variant="tonal"
          size="small"
          color="primary"
          :disabled="agentLocked"
          @click="emit('enrich')"
        >
          <v-icon start size="15">mdi-creation-outline</v-icon>
          Generate with AI
        </v-btn>
        <v-btn variant="text" size="small" @click="emit('startEdit')">
          <v-icon start size="15">mdi-pencil-outline</v-icon>
          Write manually
        </v-btn>
      </div>
    </div>
  </div>
</template>

<style scoped>
.phase-prompt-panel {
  padding: 16px;
  max-width: 720px;
  margin: 0 auto;
}

.prompt-wrapper {
  position: relative;
  background: rgb(var(--v-theme-surface-variant));
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 6px;
  padding: 12px;
  padding-top: 40px;
}

.prompt-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  color: rgb(var(--v-theme-on-surface));
  margin: 0;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
}
</style>
