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
        <v-btn variant="text" prepend-icon="mdi-arrow-left" :to="{ name: 'settings' }">
          Back to Settings
        </v-btn>
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
          :key="skill.skillSlug"
          variant="outlined"
          class="skill-card"
        >
          <!-- Collapsed header — always visible -->
          <v-card-text
            class="d-flex align-center ga-3 cursor-pointer"
            @click="toggle(skill.skillSlug)"
          >
            <v-icon
              :icon="expanded === skill.skillSlug ? 'mdi-chevron-down' : 'mdi-chevron-right'"
              size="20"
            />
            <v-icon icon="mdi-robot-outline" size="20" color="secondary" />
            <span class="text-body-1 font-weight-medium flex-grow-1">
              {{ skill.name }}
            </span>
            <v-chip
              v-if="skill.isCustomized"
              color="warning"
              variant="tonal"
              size="x-small"
              label
            >
              CUSTOMIZED
            </v-chip>
            <span class="text-caption text-medium-emphasis">
              {{ skill.skillSlug }}
            </span>
          </v-card-text>

          <!-- Expanded editor -->
          <template v-if="expanded === skill.skillSlug">
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

              <div class="d-flex ga-4 mb-4">
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
                  @click="saveSkill(skill.skillSlug)"
                >
                  Save
                </v-btn>
                <v-btn variant="text" @click="expanded = null">
                  Cancel
                </v-btn>
                <v-spacer />
                <v-btn
                  v-if="skill.isCustomized"
                  variant="tonal"
                  color="warning"
                  :loading="store.saving"
                  @click="confirmResetSlug = skill.skillSlug"
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
          <strong>{{ confirmResetSlug }}</strong> and restore the original prompt.
          This cannot be undone.
        </div>
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="confirmResetSlug = null">Cancel</v-btn>
          <v-btn color="warning" variant="flat" :loading="store.saving" @click="doReset">
            Reset
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAgentSkillsStore } from '@/stores/agentSkills'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const store = useAgentSkillsStore()

const expanded = ref<string | null>(null)
const previewMode = ref<'edit' | 'preview'>('edit')
const confirmResetSlug = ref<string | null>(null)

const showResetDialog = computed({
  get: () => confirmResetSlug.value !== null,
  set: (v: boolean) => { if (!v) confirmResetSlug.value = null },
})

const modelOptions = [
  { title: 'Default', value: '' },
  { title: 'Sonnet', value: 'sonnet' },
  { title: 'Opus', value: 'opus' },
  { title: 'Haiku', value: 'haiku' },
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
  model: '',
  effort: '',
})

function toggle(slug: string): void {
  if (expanded.value === slug) {
    expanded.value = null
    return
  }
  expanded.value = slug
  previewMode.value = 'edit'
  const skill = store.skills.find(s => s.skillSlug === slug)
  if (skill) {
    editForm.value = {
      name: skill.name,
      description: skill.description,
      tools: [...skill.tools],
      mcpTools: [...skill.mcpTools],
      prompt: skill.prompt,
      maxTurns: skill.maxTurns,
      model: skill.model ?? '',
      effort: skill.effort ?? '',
    }
  }
}

const renderedPreview = computed(() => {
  if (!editForm.value.prompt) return ''
  const raw = marked.parse(editForm.value.prompt, { async: false }) as string
  return DOMPurify.sanitize(raw)
})

async function saveSkill(slug: string): Promise<void> {
  await store.updateSkill(slug, {
    name: editForm.value.name,
    description: editForm.value.description,
    tools: editForm.value.tools,
    mcpTools: editForm.value.mcpTools,
    prompt: editForm.value.prompt,
    maxTurns: editForm.value.maxTurns,
    model: editForm.value.model,
    effort: editForm.value.effort,
  })
}

async function doReset(): Promise<void> {
  if (!confirmResetSlug.value) return
  const slug = confirmResetSlug.value
  const ok = await store.resetSkill(slug)
  confirmResetSlug.value = null
  if (ok) {
    expanded.value = null
  }
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
