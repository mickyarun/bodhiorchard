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
  <div class="settings-page">
    <!-- Header -->
    <div class="settings-header pa-6 pb-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h5 font-weight-bold">Agent Prompts</div>
          <div class="text-body-2 text-medium-emphasis">
            Customize the instructions given to each AI agent skill
          </div>
        </div>
        <div class="d-flex ga-2 align-center">
          <v-btn
            color="primary"
            variant="flat"
            prepend-icon="mdi-plus"
            @click="showCreateDialog = true"
          >
            Add Custom Skill
          </v-btn>
          <v-btn variant="text" prepend-icon="mdi-arrow-left" :to="{ name: 'settings' }">
            Back to Settings
          </v-btn>
        </div>
      </div>

      <v-alert v-if="store.error" type="error" variant="tonal" class="mt-4" closable>
        {{ store.error }}
      </v-alert>
      <v-alert
        v-if="store.saveSuccess"
        type="success"
        variant="tonal"
        class="mt-4"
        closable
        @click:close="store.saveSuccess = false"
      >
        Skill saved successfully.
      </v-alert>
    </div>

    <!-- Content -->
    <div class="px-6 pb-6">
      <!-- Loading -->
      <div v-if="store.loading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <!-- Empty state -->
      <div v-else-if="store.skills.length === 0" class="text-center py-12">
        <v-icon icon="mdi-robot-outline" size="48" class="mb-4" style="opacity: 0.3" />
        <div class="text-body-1 text-medium-emphasis">
          No agent skills found.
        </div>
      </div>

      <!-- Skill cards -->
      <div v-else class="d-flex flex-column ga-3">
        <v-card
          v-for="skill in store.skills"
          :key="skillKey(skill)"
          variant="outlined"
          class="skill-card"
        >
          <!-- Collapsed header — always visible -->
          <v-card-text
            class="d-flex align-center ga-3 cursor-pointer"
            @click="toggle(skill)"
          >
            <v-icon
              :icon="expanded === skillKey(skill) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
              size="20"
            />
            <v-icon icon="mdi-robot-outline" size="20" color="secondary" />
            <span class="text-body-1 font-weight-medium flex-grow-1">
              {{ skill.name }}
            </span>
            <v-chip
              v-if="skill.isDefault"
              color="primary"
              variant="tonal"
              size="x-small"
              label
            >
              DEFAULT
            </v-chip>
            <v-chip
              v-if="skill.isCustom"
              color="secondary"
              variant="tonal"
              size="x-small"
              label
            >
              CUSTOM
            </v-chip>
            <v-chip
              v-if="skill.isCustomized && !skill.isCustom"
              color="warning"
              variant="tonal"
              size="x-small"
              label
            >
              CUSTOMIZED
            </v-chip>
            <v-chip variant="text" size="x-small" label>
              {{ agentTypeLabel(skill.agentType) }}
            </v-chip>
            <span class="text-caption text-medium-emphasis">
              {{ skill.skillSlug }}
            </span>
          </v-card-text>

          <!-- Expanded editor -->
          <template v-if="expanded === skillKey(skill)">
            <v-divider />
            <v-card-text class="pt-4">
              <div class="d-flex ga-4 mb-4">
                <v-text-field
                  v-model="editForm.name"
                  label="Name"
                  variant="outlined"
                  density="compact"
                  hide-details
                  class="flex-grow-1"
                />
                <v-text-field
                  v-model="editForm.description"
                  label="Description"
                  variant="outlined"
                  density="compact"
                  hide-details
                  class="flex-grow-1"
                  style="flex: 2"
                />
              </div>

              <div class="d-flex ga-4 mb-4">
                <v-combobox
                  v-model="editForm.tools"
                  label="Tools"
                  variant="outlined"
                  density="compact"
                  hide-details
                  multiple
                  chips
                  closable-chips
                  class="flex-grow-1"
                />
                <v-combobox
                  v-model="editForm.mcpTools"
                  label="MCP Tools"
                  variant="outlined"
                  density="compact"
                  hide-details
                  multiple
                  chips
                  closable-chips
                  class="flex-grow-1"
                />
              </div>

              <div class="d-flex ga-4 mb-4 flex-wrap">
                <v-select
                  v-model="editForm.model"
                  :items="modelOptions"
                  item-title="title"
                  item-value="value"
                  label="Model"
                  variant="outlined"
                  density="compact"
                  hide-details
                  style="max-width: 180px"
                />
                <v-select
                  v-model="editForm.iterationModel"
                  :items="iterationModelOptions"
                  item-title="title"
                  item-value="value"
                  label="Iteration Model"
                  variant="outlined"
                  density="compact"
                  hint="Faster model for chat follow-ups; empty = use Model"
                  persistent-hint
                  style="max-width: 220px"
                />
                <v-select
                  v-model="editForm.effort"
                  :items="effortOptions"
                  item-title="title"
                  item-value="value"
                  label="Effort"
                  variant="outlined"
                  density="compact"
                  hide-details
                  style="max-width: 180px"
                />
                <v-text-field
                  v-model.number="editForm.maxTurns"
                  label="Max Turns"
                  type="number"
                  variant="outlined"
                  density="compact"
                  :min="0"
                  :max="100"
                  hint="0 = no limit"
                  persistent-hint
                  style="max-width: 140px"
                />
                <v-text-field
                  v-model.number="editForm.timeoutSeconds"
                  label="Timeout (seconds)"
                  type="number"
                  variant="outlined"
                  density="compact"
                  :min="0"
                  :max="3600"
                  hint="0 = agent default"
                  persistent-hint
                  style="max-width: 170px"
                />
              </div>

              <!-- Preview toggle -->
              <div class="d-flex align-center mb-2">
                <span class="text-body-2 font-weight-medium flex-grow-1">Prompt</span>
                <v-btn-toggle v-model="previewMode" mandatory density="compact" variant="outlined">
                  <v-btn value="edit" size="small">
                    <v-icon start size="14">mdi-pencil-outline</v-icon>
                    Edit
                  </v-btn>
                  <v-btn value="preview" size="small">
                    <v-icon start size="14">mdi-eye-outline</v-icon>
                    Preview
                  </v-btn>
                </v-btn-toggle>
              </div>

              <v-textarea
                v-if="previewMode === 'edit'"
                v-model="editForm.prompt"
                variant="outlined"
                auto-grow
                :rows="12"
                class="prompt-editor"
                hide-details
              />
              <div
                v-else
                class="preview-content rendered-markdown"
                v-html="renderedPreview"
              />

              <!-- Actions -->
              <div class="d-flex align-center ga-2 mt-4">
                <v-btn
                  color="primary"
                  variant="flat"
                  :loading="store.saving"
                  @click="saveSkill(skill)"
                >
                  Save
                </v-btn>
                <v-btn variant="text" @click="expanded = null">
                  Cancel
                </v-btn>
                <v-btn
                  v-if="!skill.isDefault && skill.id"
                  variant="tonal"
                  color="primary"
                  :loading="store.saving"
                  @click="store.setDefault(skill.id)"
                >
                  <v-icon start size="16">mdi-star-outline</v-icon>
                  Set as Default
                </v-btn>
                <v-spacer />
                <v-btn
                  v-if="skill.isCustom && skill.id"
                  variant="tonal"
                  color="error"
                  :loading="store.saving"
                  @click="confirmDeleteId = skill.id"
                >
                  <v-icon start size="16">mdi-delete-outline</v-icon>
                  Delete
                </v-btn>
                <v-btn
                  v-else-if="skill.isCustomized"
                  variant="tonal"
                  color="warning"
                  :loading="store.saving"
                  @click="confirmResetTarget = { slug: skill.skillSlug, agentType: skill.agentType }"
                >
                  <v-icon start size="16">mdi-restore</v-icon>
                  Reset to Default
                </v-btn>
              </div>
            </v-card-text>
          </template>
        </v-card>
      </div>
    </div>

    <!-- Reset confirmation dialog -->
    <v-dialog v-model="showResetDialog" max-width="400">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 mb-2">Reset to Default?</div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          This will discard your customizations for
          <strong>{{ confirmResetTarget?.slug }}</strong> and restore the original prompt.
          This cannot be undone.
        </div>
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="confirmResetTarget = null">Cancel</v-btn>
          <v-btn color="warning" variant="flat" :loading="store.saving" @click="doReset">
            Reset
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Delete-custom confirmation dialog -->
    <v-dialog v-model="showDeleteDialog" max-width="400">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 mb-2">Delete custom skill?</div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          This permanently removes the custom skill. Any BUDs that referenced
          it directly will fall back to the agent default.
        </div>
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="confirmDeleteId = null">Cancel</v-btn>
          <v-btn color="error" variant="flat" :loading="store.saving" @click="doDelete">
            Delete
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <CustomSkillDialog v-model="showCreateDialog" @created="onCustomCreated" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAgentSkillsStore, AGENT_TYPE_LABELS, type AgentSkill, type AgentType } from '@/stores/agentSkills'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import CustomSkillDialog from './CustomSkillDialog.vue'

const store = useAgentSkillsStore()

const expanded = ref<string | null>(null)
const previewMode = ref<'edit' | 'preview'>('edit')
const confirmResetTarget = ref<{ slug: string; agentType: AgentType } | null>(null)
const confirmDeleteId = ref<string | null>(null)
const showCreateDialog = ref(false)

const showResetDialog = computed({
  get: () => confirmResetTarget.value !== null,
  set: (v: boolean) => { if (!v) confirmResetTarget.value = null },
})

const showDeleteDialog = computed({
  get: () => confirmDeleteId.value !== null,
  set: (v: boolean) => { if (!v) confirmDeleteId.value = null },
})

function skillKey(skill: AgentSkill): string {
  return `${skill.skillSlug}__${skill.agentType}`
}

function agentTypeLabel(at: AgentType): string {
  return AGENT_TYPE_LABELS[at] ?? at
}

const modelOptions = [
  { title: 'Default', value: '' },
  { title: 'Sonnet', value: 'sonnet' },
  { title: 'Opus', value: 'opus' },
  { title: 'Haiku', value: 'haiku' },
]

// Iteration model is for chat follow-ups (e.g. BUD design hot loop). Empty
// falls back to ``model``. Explicit Haiku 4.5 is the common pick for
// "fast cheap iteration on a stable design system".
const iterationModelOptions = [
  { title: 'Same as Model', value: '' },
  { title: 'Sonnet', value: 'sonnet' },
  { title: 'Opus', value: 'opus' },
  { title: 'Haiku', value: 'haiku' },
  { title: 'Haiku 4.5', value: 'claude-haiku-4-5' },
]

const effortOptions = [
  { title: 'Default', value: '' },
  { title: 'Low', value: 'low' },
  { title: 'Medium', value: 'medium' },
  { title: 'High', value: 'high' },
  { title: 'Max', value: 'max' },
]

const editForm = ref({
  name: '',
  description: '',
  tools: [] as string[],
  mcpTools: [] as string[],
  prompt: '',
  maxTurns: 0,
  timeoutSeconds: 0,
  model: '',
  iterationModel: '',
  effort: '',
})

function toggle(skill: AgentSkill): void {
  const key = skillKey(skill)
  if (expanded.value === key) {
    expanded.value = null
    return
  }
  expanded.value = key
  previewMode.value = 'edit'
  editForm.value = {
    name: skill.name,
    description: skill.description,
    tools: [...skill.tools],
    mcpTools: [...skill.mcpTools],
    prompt: skill.prompt,
    maxTurns: skill.maxTurns,
    timeoutSeconds: skill.timeoutSeconds ?? 0,
    model: skill.model ?? '',
    iterationModel: skill.iterationModel ?? '',
    effort: skill.effort ?? '',
  }
}

const renderedPreview = computed(() => {
  if (!editForm.value.prompt) return ''
  const raw = marked.parse(editForm.value.prompt, { async: false }) as string
  return DOMPurify.sanitize(raw)
})

async function saveSkill(skill: AgentSkill): Promise<void> {
  await store.updateSkill(skill.skillSlug, skill.agentType, {
    name: editForm.value.name,
    description: editForm.value.description,
    tools: editForm.value.tools,
    mcpTools: editForm.value.mcpTools,
    prompt: editForm.value.prompt,
    maxTurns: editForm.value.maxTurns,
    timeoutSeconds: editForm.value.timeoutSeconds,
    model: editForm.value.model,
    iterationModel: editForm.value.iterationModel,
    effort: editForm.value.effort,
  })
}

async function doReset(): Promise<void> {
  const target = confirmResetTarget.value
  if (!target) return
  const ok = await store.resetSkill(target.slug, target.agentType)
  confirmResetTarget.value = null
  if (ok) expanded.value = null
}

async function doDelete(): Promise<void> {
  const id = confirmDeleteId.value
  if (!id) return
  const ok = await store.deleteCustomSkill(id)
  confirmDeleteId.value = null
  if (ok) expanded.value = null
}

function onCustomCreated(): void {
  showCreateDialog.value = false
}

onMounted(() => {
  store.fetchSkills()
})
</script>

<style scoped>
.settings-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.settings-header {
  flex-shrink: 0;
}

.skill-card {
  border-color: rgba(var(--v-theme-on-surface), 0.08) !important;
}

.skill-card .v-btn {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
}

.prompt-editor :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.6;
}

.preview-content {
  max-height: 500px;
  overflow-y: auto;
  padding: 16px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border-radius: 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  font-size: 13px;
  line-height: 1.7;
}

.preview-content :deep(h1),
.preview-content :deep(h2),
.preview-content :deep(h3) {
  margin: 12px 0 6px;
}

.preview-content :deep(h1) { font-size: 1.3em; }
.preview-content :deep(h2) { font-size: 1.1em; }
.preview-content :deep(h3) { font-size: 1em; }

.preview-content :deep(code) {
  background: rgba(var(--v-theme-on-surface), 0.07);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.87em;
}

.preview-content :deep(pre) {
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 6px;
  padding: 12px 16px;
  margin: 8px 0;
  overflow-x: auto;
}

.preview-content :deep(pre code) {
  background: none;
  padding: 0;
}

.preview-content :deep(ul),
.preview-content :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}

.preview-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 12px;
}

.preview-content :deep(th),
.preview-content :deep(td) {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  padding: 6px 10px;
  text-align: left;
}

.preview-content :deep(th) {
  background: rgba(var(--v-theme-on-surface), 0.04);
  font-weight: 600;
}
</style>
