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
import BUDImpactedReposDialog from '@/components/buds/BUDImpactedReposDialog.vue'
import { useMermaidRender } from '@/composables/useMermaidRender'
import type { BUDDocument } from '@/types'
import { renderMarkdown } from '@/utils/markdown'
import { techArchPrompt } from '@/utils/budPromptTemplates'
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
  generate: []
  /** Fired after the user saves an impacted_repos edit so the parent
   *  reloads the BUD and every repo-derived surface refreshes. */
  'refresh-bud': []
}>()

// Impacted-repos edit dialog. Tech Arch is where repo scope is first
// decided (and where the agent's first guess most often needs correcting),
// so the same Edit affordance the Development tab offers lives here too.
const editReposOpen = ref(false)

// True when the PM has explicitly disabled the AI tech-arch agent
// for this BUD. The empty / unset case ALSO returns true (default is
// "external-LLM mode"). Mirrors the backend's
// ``should_auto_generate_phase`` predicate
// (services/bud_agent_trigger.py).
const techArchAutoOff = computed(
  () => props.bud.auto_generate_phases?.tech_arch !== true,
)

// Show the local-Claude prompt panel whenever the PM has opted out of
// auto-generation AND the spec is still empty — regardless of whether
// a Figma URL is set. When ``figma_url`` is absent the template shows
// a "<PASTE FIGMA URL HERE>" placeholder so the prompt is still
// copy-paste ready.
const showLocalClaudePanel = computed(
  () => !props.bud.tech_spec_md && techArchAutoOff.value,
)

// Prompt template using the shared tech-arch template. Pre-fills the
// BUD number, id, and optionally the Figma URL so the developer never
// has to substitute placeholders by hand.
const promptText = computed(
  () => techArchPrompt(props.bud.bud_number, props.bud.id, props.bud.figma_url),
)

const copied = ref(false)

// Template ref to the rendered-markdown container. The composable
// finds any ``<pre class="mermaid">`` blocks inside this element on
// mount + every update and replaces them with rendered SVG.
const renderedSpecRef = ref<HTMLElement | null>(null)
useMermaidRender(renderedSpecRef)

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
    <!-- Impacted repos — editable here so the scope can be corrected while
         the tech spec is being planned (the tech-arch agent's first guess
         often needs fixing). Hidden while editing the spec markdown to keep
         that focused. Same dialog + contract as the Development tab. -->
    <div
      v-if="!editing"
      class="d-flex align-center flex-wrap ga-2 mb-4 tech-spec-impacted-row"
    >
      <v-icon icon="mdi-source-repository-multiple" size="16" color="medium-emphasis" />
      <span class="text-caption text-medium-emphasis">Impacted:</span>
      <template v-if="bud.impacted_repos && bud.impacted_repos.length">
        <v-chip
          v-for="r in bud.impacted_repos"
          :key="r.repo_id || r.repo_name"
          size="x-small"
          variant="tonal"
          prepend-icon="mdi-source-repository"
        >
          {{ r.repo_name }}
        </v-chip>
      </template>
      <span v-else class="text-caption text-medium-emphasis">none yet</span>
      <v-spacer />
      <v-btn
        size="x-small"
        variant="text"
        density="compact"
        prepend-icon="mdi-pencil-outline"
        @click="editReposOpen = true"
      >
        Edit
      </v-btn>
    </div>

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
      ref="renderedSpecRef"
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

      <div class="d-flex ga-2 mt-3">
        <v-btn
          v-if="!bud.figma_url"
          variant="tonal"
          size="small"
          color="primary"
          :disabled="bud.status !== 'tech_arch'"
          :title="bud.status !== 'tech_arch' ? 'Move the BUD to Tech Arch phase to generate' : ''"
          @click="emit('generate')"
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
    <!-- Auto-generate ON but spec not yet written — simple empty state.
         The agent handles generation on phase transition; no prompt
         panel needed here. -->
    <div v-else class="section-empty">
      <v-icon icon="mdi-code-braces" size="40" class="mb-3" />
      <div>No tech spec yet</div>
      <div class="text-caption text-medium-emphasis mt-1 mb-3">
        The AI agent will generate this automatically
      </div>
      <div class="d-flex ga-2">
        <v-btn
          v-if="!bud.figma_url"
          variant="tonal"
          size="small"
          color="primary"
          :disabled="bud.status !== 'tech_arch'"
          :title="bud.status !== 'tech_arch' ? 'Move the BUD to Tech Arch phase to generate' : ''"
          @click="emit('generate')"
        >
          <v-icon start size="15">mdi-creation-outline</v-icon>
          Generate with AI
        </v-btn>
        <v-btn variant="text" size="small" @click="emit('startEdit')">
          <v-icon start size="15">mdi-pencil-outline</v-icon>
          Start writing
        </v-btn>
      </div>
    </div>

    <BUDImpactedReposDialog
      v-model="editReposOpen"
      :bud-id="bud.id"
      :current="bud.impacted_repos ?? null"
      @saved="emit('refresh-bud')"
    />
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
