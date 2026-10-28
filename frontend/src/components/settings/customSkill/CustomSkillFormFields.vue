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

<!-- Field grid of the "New custom skill" dialog. Writes straight into the
     dialog-owned form; a paste into Prompt is handed back for import. -->
<template>
  <div class="field-grid">
    <div class="field col-6">
      <label class="field-label">Agent type</label>
      <v-select
        v-model="form.agentType"
        :items="AGENT_TYPE_ITEMS"
        item-title="title"
        item-value="value"
        variant="outlined"
        density="compact"
        hide-details
      />
    </div>

    <div class="field col-6">
      <label class="field-label">Slug</label>
      <v-text-field
        v-model="form.skillSlug"
        placeholder="my-pm"
        variant="outlined"
        density="compact"
        :error-messages="slugMessage ? [slugMessage] : []"
        hide-details="auto"
      />
      <div v-if="!slugMessage" class="field-hint">
        Lowercase, hyphens only — unique within agent type
      </div>
    </div>

    <div class="field col-12">
      <label class="field-label">Display name</label>
      <v-text-field
        v-model="form.name"
        placeholder="e.g. Concise PM"
        variant="outlined"
        density="compact"
        hide-details
      />
    </div>

    <div class="field col-12">
      <label class="field-label">Description</label>
      <v-text-field
        v-model="form.description"
        placeholder="One line shown next to the skill name"
        variant="outlined"
        density="compact"
        hide-details
      />
    </div>

    <div class="field col-12">
      <label class="field-label">Prompt</label>
      <v-textarea
        v-model="form.prompt"
        placeholder="# Skill&#10;&#10;You are…"
        variant="outlined"
        density="compact"
        rows="9"
        auto-grow
        hide-details
        class="prompt-textarea"
        @paste="emit('prompt-paste', $event)"
      />
      <div class="field-hint">
        Tip: paste a full <code>.md</code> file and the YAML frontmatter
        is split into the other fields automatically.
      </div>
    </div>

    <div class="field col-6">
      <label class="field-label">Tools</label>
      <v-combobox
        v-model="form.tools"
        placeholder="Read, Write, Edit…"
        variant="outlined"
        density="compact"
        multiple
        chips
        closable-chips
        hide-details
      />
    </div>

    <div class="field col-6">
      <label class="field-label">MCP tools</label>
      <v-combobox
        v-model="form.mcpTools"
        placeholder="get_bud_context…"
        variant="outlined"
        density="compact"
        multiple
        chips
        closable-chips
        hide-details
      />
    </div>

    <div class="field col-6">
      <label class="field-label">Model</label>
      <v-select
        v-model="form.model"
        :items="CUSTOM_SKILL_MODEL_OPTIONS"
        item-title="title"
        item-value="value"
        variant="outlined"
        density="compact"
        hide-details
      />
    </div>

    <div class="field col-6">
      <label class="field-label">Max turns</label>
      <v-text-field
        v-model.number="form.maxTurns"
        type="number"
        :min="0"
        :max="100"
        variant="outlined"
        density="compact"
        hide-details
      />
      <div class="field-hint">0 = unlimited</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  AGENT_TYPE_ITEMS,
  CUSTOM_SKILL_MODEL_OPTIONS,
  slugError,
  type CustomSkillForm,
} from './customSkillForm.util'

const form = defineModel<CustomSkillForm>('form', { required: true })
const emit = defineEmits<{ 'prompt-paste': [event: ClipboardEvent] }>()

const slugMessage = computed(() => slugError(form.value.skillSlug))
</script>

<style scoped>
.field-hint code {
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 10.5px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  padding: 1px 4px;
  border-radius: 3px;
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  column-gap: 12px;
  row-gap: 14px;
}

.col-6 { grid-column: span 6; }
.col-12 { grid-column: 1 / -1; }

@media (max-width: 600px) {
  .col-6 { grid-column: 1 / -1; }
}

.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.field-label {
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0;
  color: rgba(var(--v-theme-on-surface), 0.78);
  line-height: 1;
}

.field-hint {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  line-height: 1.3;
  margin-top: 1px;
}

.prompt-textarea :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.55;
}

.prompt-textarea :deep(.v-field) {
  background: rgb(var(--v-theme-background));
}
</style>
