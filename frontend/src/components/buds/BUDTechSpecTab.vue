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

import AppCallout from '@/components/common/AppCallout.vue'
import type { BUDDocument } from '@/types'
import { renderMarkdown } from '@/utils/markdown'
import './bud-section.css'

const props = defineProps<{
  bud: BUDDocument
  editing: boolean
  editValue: string
}>()

const emit = defineEmits<{
  'update:editValue': [value: string]
  save: []
  startEdit: []
}>()

// True when the PM has explicitly disabled the AI tech-arch agent
// for this BUD. The empty / unset case ALSO returns true (default is
// "external-LLM mode"). Mirrors the backend's
// ``should_auto_generate_phase`` predicate
// (services/bud_agent_trigger.py).
const techArchAutoOff = computed(
  () => props.bud.auto_generate_phases?.tech_arch !== true,
)

// Show the local-Claude prompt panel only when the BUD is genuinely
// Figma-driven: ``figma_url`` is set AND auto-tech-arch is off AND
// the spec is still empty. Without a Figma URL the prompt has
// nothing to extract from, so the panel would be useless noise — we
// fall back to the original "Start writing" empty state instead.
const showLocalClaudePanel = computed(
  () =>
    !props.bud.tech_spec_md
    && techArchAutoOff.value
    && !!props.bud.figma_url,
)

// Prompt template the developer pastes into their local Claude
// Code. Single source of truth — keeps the wording aligned with
// the tech-planner skill's "Figma flow extraction" sub-section.
// When ``figma_url`` is unset we leave the placeholder so the PM
// can paste the URL inline before sending.
const promptText = computed(
  () => `Generate tech spec for BUD-${props.bud.bud_number} (id: ${props.bud.id}).
Figma URL: ${props.bud.figma_url || '<PASTE FIGMA URL HERE>'}

Use get_prompt(task_type="tech_plan"). Follow its Figma flow extraction sub-section:
read frames via local Figma MCP frame-by-frame, build a Mermaid flow chart,
derive corner cases exhaustively from the flow chart. Write back via update_bud.`,
)

const copied = ref(false)

async function copyPrompt(): Promise<void> {
  try {
    await navigator.clipboard.writeText(promptText.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 2000)
  } catch {
    // Non-secure context (HTTP without localhost) — fall back silently.
    // The textarea below stays selectable so the user can copy by hand.
  }
}
</script>

<template>
  <div class="bud-tech-spec-tab">
    <textarea
      v-if="editing"
      :value="editValue"
      class="section-editor"
      placeholder="Technical implementation details..."
      @input="emit('update:editValue', ($event.target as HTMLTextAreaElement).value)"
      @blur="emit('save')"
    />
    <div
      v-else-if="bud.tech_spec_md"
      class="rendered-markdown"
      v-html="renderMarkdown(bud.tech_spec_md)"
    />
    <!--
      Local-Claude prompt panel — shown when the PM has opted out of
      auto-generation. The dev pastes the prompt into their own
      Claude Code session (which has local Figma MCP via the Figma
      Desktop app); the agent extracts frames, builds the flow chart,
      and writes the spec back via update_bud. Mirrors the contract
      documented in backend/app/agents/skills/tech-planner.md.
     -->
    <div v-else-if="showLocalClaudePanel" class="local-claude-panel">
      <AppCallout
        variant="info"
        eyebrow="Generate tech spec locally"
        icon="mdi-console-line"
        class="mb-4"
      >
        Auto-generation is off for this BUD. Paste the prompt below
        into your local Claude Code session — it'll use Figma MCP
        (via Figma Desktop's Dev Mode) to read frames, build a flow
        chart, derive corner cases, and write the spec back here.
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
            {{ copied ? 'mdi-check' : 'mdi-content-copy' }}
          </v-icon>
          {{ copied ? 'Copied' : 'Copy prompt' }}
        </v-btn>
      </div>

      <div class="text-caption text-medium-emphasis mt-3">
        Requires Figma Desktop running with "Enable Dev Mode MCP
        Server" toggled on, and your local Claude Code connected to
        this BUD's MCP endpoint. Or click "Start writing" to draft
        the spec by hand.
      </div>

      <v-btn variant="text" size="small" class="mt-3" @click="emit('startEdit')">
        <v-icon start size="15">mdi-pencil-outline</v-icon>
        Start writing manually
      </v-btn>
    </div>
    <div v-else class="section-empty">
      <v-icon icon="mdi-code-braces" size="40" class="mb-3" />
      <div>No tech spec yet</div>
      <v-btn variant="tonal" size="small" class="mt-3" @click="emit('startEdit')">
        <v-icon start size="15">mdi-pencil-outline</v-icon>
        Start writing
      </v-btn>
    </div>
  </div>
</template>

<style scoped>
.local-claude-panel {
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
