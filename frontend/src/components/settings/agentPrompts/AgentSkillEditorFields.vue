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

<!-- The field grid of the inline skill editor. Writes straight into the
     page-owned edit form; model/effort options follow the active provider. -->
<template>
  <div class="editor-grid">
    <div class="field col-6">
      <label class="field-label">Name</label>
      <v-text-field v-model="form.name" variant="outlined" density="compact" hide-details />
    </div>
    <div class="field col-6">
      <label class="field-label">Description</label>
      <v-text-field v-model="form.description" variant="outlined" density="compact" hide-details />
    </div>

    <div class="field col-6">
      <label class="field-label">Tools</label>
      <v-combobox
        v-model="form.tools"
        placeholder="Type and press enter"
        variant="outlined"
        density="compact"
        hide-details
        multiple
        chips
        closable-chips
      />
    </div>
    <div class="field col-6">
      <label class="field-label">MCP tools</label>
      <v-combobox
        v-model="form.mcpTools"
        placeholder="get_bud_context, write_bud, …"
        variant="outlined"
        density="compact"
        hide-details
        multiple
        chips
        closable-chips
      />
    </div>

    <div class="field col-2">
      <label class="field-label">Model</label>
      <v-select
        v-model="form.model"
        :items="modelItems"
        item-title="title"
        item-value="value"
        variant="outlined"
        density="compact"
        hide-details
        :disabled="!modelChoice"
      />
    </div>
    <div v-if="caps.supportsIterationModel && modelChoice" class="field col-2">
      <label class="field-label">Iteration model</label>
      <v-select
        v-model="form.iterationModel"
        :items="iterationModelItems"
        item-title="title"
        item-value="value"
        variant="outlined"
        density="compact"
        hide-details
      />
    </div>
    <div v-if="caps.supportsEffort" class="field col-2">
      <label class="field-label">Effort</label>
      <v-select
        v-model="form.effort"
        :items="effortItems"
        item-title="title"
        item-value="value"
        variant="outlined"
        density="compact"
        hide-details
      />
    </div>
    <div class="field col-2">
      <label class="field-label">Max turns</label>
      <v-text-field
        v-model.number="form.maxTurns"
        type="number" :min="0" :max="100" variant="outlined" density="compact" hide-details
      />
    </div>
    <div class="field col-2">
      <label class="field-label">Iteration max turns</label>
      <v-text-field
        v-model.number="form.iterationMaxTurns"
        type="number" :min="1" :max="100" variant="outlined" density="compact" hide-details
      />
    </div>
    <div class="field col-2">
      <label class="field-label">Timeout (s)</label>
      <v-text-field
        v-model.number="form.timeoutSeconds"
        type="number" :min="0" :max="3600" variant="outlined" density="compact" hide-details
      />
    </div>

    <div class="field col-12">
      <div class="d-flex align-center justify-space-between">
        <label class="field-label">Prompt</label>
        <AppPillToggle v-model="previewMode" :options="PREVIEW_MODE_OPTIONS" size="sm" />
      </div>
      <AgentSkillPromptBody v-model:prompt="form.prompt" :mode="previewMode" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import AgentSkillPromptBody from './AgentSkillPromptBody.vue'
import {
  effortOptions,
  iterationModelOptions,
  modelOptions,
  supportsModelChoice,
  type SkillCaps,
} from './skillCapabilities.util'
import { PREVIEW_MODE_OPTIONS, type PreviewMode, type SkillEditForm } from './skillEditForm.util'

const props = defineProps<{ caps: SkillCaps }>()
const form = defineModel<SkillEditForm>('form', { required: true })
const previewMode = defineModel<PreviewMode>('previewMode', { required: true })

const modelChoice = computed(() => supportsModelChoice(props.caps))
const modelItems = computed(() => modelOptions(props.caps, form.value?.model))
const iterationModelItems = computed(() => iterationModelOptions(props.caps, form.value?.iterationModel))
const effortItems = computed(() => effortOptions(props.caps))
</script>

<style scoped>
.editor-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  column-gap: 12px;
  row-gap: 12px;
  padding-top: 14px;
}

.col-2 { grid-column: span 2; }
.col-3 { grid-column: span 3; }
.col-6 { grid-column: span 6; }
.col-12 { grid-column: 1 / -1; }

@media (max-width: 1100px) {
  .col-2,
  .col-3 { grid-column: span 4; }
}
@media (max-width: 720px) {
  .col-2,
  .col-3,
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
  color: rgba(var(--v-theme-on-surface), 0.75);
  line-height: 1;
}

/* Tighten Vuetify's outlined input height now that the label lives
   outside. Compact density alone leaves a small gap that adds up
   across 9 fields. */
.editor-grid :deep(.v-field--variant-outlined .v-field__input) {
  min-height: 36px;
  padding-top: 4px;
  padding-bottom: 4px;
}
.editor-grid :deep(.v-input--density-compact .v-input__details) {
  min-height: 0;
}
</style>
