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
    <!-- Page header -->
    <header class="page-header pa-6 pb-5">
      <div class="d-flex align-start justify-space-between flex-wrap ga-4">
        <div>
          <div class="d-flex align-center ga-2 mb-1">
            <v-icon icon="mdi-robot-happy-outline" size="22" color="primary" />
            <h1 class="page-title">Agent Prompts</h1>
          </div>
          <div class="page-subtitle">
            Tune the persona, tooling, and prompt that drives each AI agent
            skill. Add your own and pick a default per agent type.
          </div>
        </div>
        <div class="d-flex ga-2 align-center">
          <v-btn
            color="primary"
            variant="flat"
            prepend-icon="mdi-plus"
            class="text-none"
            @click="showCreateDialog = true"
          >
            Add custom skill
          </v-btn>
          <v-btn
            variant="text"
            prepend-icon="mdi-arrow-left"
            class="text-none text-medium-emphasis"
            :to="{ name: 'settings' }"
          >
            Back to settings
          </v-btn>
        </div>
      </div>

      <!-- Search + filter -->
      <div class="d-flex align-center ga-3 mt-5 flex-wrap">
        <v-text-field
          v-model="search"
          placeholder="Search skills, descriptions, slugs…"
          prepend-inner-icon="mdi-magnify"
          variant="solo-filled"
          density="compact"
          hide-details
          flat
          single-line
          class="search-input"
          clearable
        />
        <v-chip-group
          v-model="filterMode"
          mandatory
          selected-class="filter-chip-selected"
          class="filter-chips"
        >
          <v-chip value="all" variant="tonal" size="small" filter>All</v-chip>
          <v-chip value="custom" variant="tonal" size="small" filter>Custom</v-chip>
          <v-chip value="modified" variant="tonal" size="small" filter>Modified</v-chip>
        </v-chip-group>
      </div>

      <v-alert
        v-if="store.error"
        type="error"
        variant="tonal"
        class="mt-4"
        density="compact"
        closable
      >
        {{ store.error }}
      </v-alert>
      <v-alert
        v-if="store.saveSuccess"
        type="success"
        variant="tonal"
        class="mt-4"
        density="compact"
        closable
        @click:close="store.saveSuccess = false"
      >
        Saved.
      </v-alert>
    </header>

    <!-- Content -->
    <div class="page-content px-6 pb-8">
      <div v-if="store.loading" class="d-flex justify-center py-16">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <div v-else-if="store.skills.length === 0" class="empty-state">
        <v-icon icon="mdi-robot-confused-outline" size="48" />
        <div class="empty-title">No agent skills yet</div>
        <div class="empty-sub">
          Skills will appear here once they're seeded from your project.
        </div>
      </div>

      <div v-else-if="filteredGroups.length === 0" class="empty-state">
        <v-icon icon="mdi-filter-remove-outline" size="48" />
        <div class="empty-title">No matches</div>
        <div class="empty-sub">Try a different search or filter.</div>
      </div>

      <!-- Agent-type groups -->
      <div v-else class="d-flex flex-column ga-5">
        <section
          v-for="group in filteredGroups"
          :key="group.agentType"
          class="agent-group"
        >
          <!-- Section header -->
          <div class="group-header">
            <div
              class="group-icon-wrap"
              :style="{ '--accent': agentAccent(group.agentType) }"
            >
              <v-icon :icon="agentIcon(group.agentType)" size="20" />
            </div>
            <div class="group-meta">
              <div class="group-title">{{ agentTypeLabel(group.agentType) }}</div>
              <div class="group-sub">{{ agentBlurb(group.agentType) }}</div>
            </div>
            <v-chip variant="tonal" size="x-small" label class="group-count">
              {{ group.skills.length }}
              skill{{ group.skills.length === 1 ? '' : 's' }}
            </v-chip>
          </div>

          <!-- Skill rows -->
          <div class="skill-list">
            <article
              v-for="skill in group.skills"
              :key="skillKey(skill)"
              class="skill-row"
              :class="{ 'is-open': expanded === skillKey(skill) }"
            >
              <!-- Compact summary row (always visible) -->
              <button
                type="button"
                class="skill-summary"
                @click="toggle(skill)"
              >
                <v-icon
                  :icon="expanded === skillKey(skill) ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                  size="18"
                  class="skill-chevron"
                />
                <div class="skill-headline">
                  <div class="skill-name-row">
                    <v-icon
                      v-if="skill.isDefault"
                      icon="mdi-star"
                      size="14"
                      color="secondary"
                      class="mr-1"
                    />
                    <span class="skill-name">{{ skill.name }}</span>
                    <v-chip
                      v-if="skill.isDefault"
                      color="primary"
                      variant="flat"
                      size="x-small"
                      label
                      class="ml-2"
                    >
                      Default
                    </v-chip>
                    <v-chip
                      v-if="skill.isCustom"
                      color="secondary"
                      variant="tonal"
                      size="x-small"
                      label
                      class="ml-2"
                    >
                      Custom
                    </v-chip>
                    <v-chip
                      v-else-if="skill.isCustomized"
                      color="warning"
                      variant="tonal"
                      size="x-small"
                      label
                      class="ml-2"
                    >
                      Modified
                    </v-chip>
                  </div>
                  <div v-if="skill.description" class="skill-desc">
                    {{ skill.description }}
                  </div>
                </div>
                <div class="skill-meta">
                  <span class="skill-meta-chip">
                    <v-icon icon="mdi-cube-outline" size="12" />
                    {{ skill.model || 'default' }}
                  </span>
                  <code class="skill-slug">{{ skill.skillSlug }}</code>
                </div>
              </button>

              <!-- Expanded editor -->
              <div v-if="expanded === skillKey(skill)" class="skill-editor">
                <v-divider />

                <div class="editor-grid">
                  <div class="field col-6">
                    <label class="field-label">Name</label>
                    <v-text-field
                      v-model="editForm.name"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                  </div>
                  <div class="field col-6">
                    <label class="field-label">Description</label>
                    <v-text-field
                      v-model="editForm.description"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                  </div>

                  <div class="field col-6">
                    <label class="field-label">Tools</label>
                    <v-combobox
                      v-model="editForm.tools"
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
                      v-model="editForm.mcpTools"
                      placeholder="get_bud_context, write_bud, …"
                      variant="outlined"
                      density="compact"
                      hide-details
                      multiple
                      chips
                      closable-chips
                    />
                  </div>

                  <div class="field col-3">
                    <label class="field-label">Model</label>
                    <v-select
                      v-model="editForm.model"
                      :items="modelOptions"
                      item-title="title"
                      item-value="value"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                  </div>
                  <div class="field col-3">
                    <label class="field-label">Iteration model</label>
                    <v-select
                      v-model="editForm.iterationModel"
                      :items="iterationModelOptions"
                      item-title="title"
                      item-value="value"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                  </div>
                  <div class="field col-2">
                    <label class="field-label">Effort</label>
                    <v-select
                      v-model="editForm.effort"
                      :items="effortOptions"
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
                      v-model.number="editForm.maxTurns"
                      type="number"
                      :min="0"
                      :max="100"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                  </div>
                  <div class="field col-2">
                    <label class="field-label">Timeout (s)</label>
                    <v-text-field
                      v-model.number="editForm.timeoutSeconds"
                      type="number"
                      :min="0"
                      :max="3600"
                      variant="outlined"
                      density="compact"
                      hide-details
                    />
                  </div>

                  <div class="field col-12">
                    <div class="d-flex align-center justify-space-between">
                      <label class="field-label">Prompt</label>
                      <v-btn-toggle
                        v-model="previewMode"
                        mandatory
                        density="compact"
                        variant="outlined"
                        divided
                      >
                        <v-btn value="edit" size="x-small" class="text-none">
                          <v-icon start size="13">mdi-pencil-outline</v-icon>
                          Edit
                        </v-btn>
                        <v-btn value="preview" size="x-small" class="text-none">
                          <v-icon start size="13">mdi-eye-outline</v-icon>
                          Preview
                        </v-btn>
                      </v-btn-toggle>
                    </div>
                    <v-textarea
                      v-if="previewMode === 'edit'"
                      v-model="editForm.prompt"
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
                  </div>
                </div>

                <!-- Action bar -->
                <div class="editor-actions">
                  <v-btn
                    color="primary"
                    variant="flat"
                    :loading="store.saving"
                    class="text-none"
                    @click="saveSkill(skill)"
                  >
                    Save changes
                  </v-btn>
                  <v-btn variant="text" class="text-none" @click="expanded = null">
                    Cancel
                  </v-btn>
                  <v-btn
                    v-if="!skill.isDefault && skill.id"
                    variant="tonal"
                    color="secondary"
                    prepend-icon="mdi-star-outline"
                    :loading="store.saving"
                    class="text-none"
                    @click="store.setDefault(skill.id)"
                  >
                    Set as default
                  </v-btn>
                  <v-spacer />
                  <v-btn
                    v-if="skill.isCustom && skill.id"
                    variant="text"
                    color="error"
                    prepend-icon="mdi-trash-can-outline"
                    :loading="store.saving"
                    class="text-none"
                    @click="confirmDeleteId = skill.id"
                  >
                    Delete skill
                  </v-btn>
                  <v-btn
                    v-else-if="skill.isCustomized"
                    variant="text"
                    color="warning"
                    prepend-icon="mdi-restore"
                    :loading="store.saving"
                    class="text-none"
                    @click="confirmResetTarget = { slug: skill.skillSlug, agentType: skill.agentType }"
                  >
                    Reset to default
                  </v-btn>
                </div>
              </div>
            </article>

            <!-- Inline add-button per group -->
            <button
              type="button"
              class="skill-add"
              @click="openCreateForAgent(group.agentType)"
            >
              <v-icon icon="mdi-plus" size="16" />
              Add a custom skill for {{ agentTypeLabel(group.agentType) }}
            </button>
          </div>
        </section>
      </div>
    </div>

    <!-- Reset confirmation -->
    <v-dialog v-model="showResetDialog" max-width="420">
      <v-card class="confirm-card">
        <div class="confirm-icon confirm-icon-warn">
          <v-icon icon="mdi-restore" size="24" />
        </div>
        <h3 class="confirm-title">Reset to default?</h3>
        <p class="confirm-body">
          Discards your customizations for
          <strong>{{ confirmResetTarget?.slug }}</strong>
          and restores the original prompt. Can't be undone.
        </p>
        <div class="confirm-actions">
          <v-btn variant="text" class="text-none" @click="confirmResetTarget = null">
            Cancel
          </v-btn>
          <v-btn
            color="warning"
            variant="flat"
            class="text-none"
            :loading="store.saving"
            @click="doReset"
          >
            Reset
          </v-btn>
        </div>
      </v-card>
    </v-dialog>

    <!-- Delete confirmation -->
    <v-dialog v-model="showDeleteDialog" max-width="420">
      <v-card class="confirm-card">
        <div class="confirm-icon confirm-icon-err">
          <v-icon icon="mdi-trash-can-outline" size="24" />
        </div>
        <h3 class="confirm-title">Delete this custom skill?</h3>
        <p class="confirm-body">
          Permanently removes the skill. BUDs that pinned it will fall
          back to the agent default.
        </p>
        <div class="confirm-actions">
          <v-btn variant="text" class="text-none" @click="confirmDeleteId = null">
            Cancel
          </v-btn>
          <v-btn
            color="error"
            variant="flat"
            class="text-none"
            :loading="store.saving"
            @click="doDelete"
          >
            Delete
          </v-btn>
        </div>
      </v-card>
    </v-dialog>

    <CustomSkillDialog
      v-model="showCreateDialog"
      :initial-agent-type="createForAgent"
      @created="onCustomCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import {
  useAgentSkillsStore,
  AGENT_TYPE_LABELS,
  type AgentSkill,
  type AgentType,
} from '@/stores/agentSkills'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import CustomSkillDialog from './CustomSkillDialog.vue'

const store = useAgentSkillsStore()

const expanded = ref<string | null>(null)
const previewMode = ref<'edit' | 'preview'>('edit')
const confirmResetTarget = ref<{ slug: string; agentType: AgentType } | null>(null)
const confirmDeleteId = ref<string | null>(null)
const showCreateDialog = ref(false)
const createForAgent = ref<AgentType | null>(null)
const search = ref('')
const filterMode = ref<'all' | 'custom' | 'modified'>('all')

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

// Visual identity per agent type — picked so each section is distinguishable
// at a glance even when scrolling fast. Colors map to Vuetify theme tokens.
const AGENT_ICONS: Record<AgentType, string> = {
  triage: 'mdi-magnify-scan',
  bud: 'mdi-clipboard-text-outline',
  status: 'mdi-pulse',
  standup: 'mdi-account-group-outline',
  learning: 'mdi-book-open-page-variant-outline',
  bugLinker: 'mdi-bug-outline',
  reassignment: 'mdi-account-switch-outline',
  skill: 'mdi-shield-check-outline',
  techPlan: 'mdi-vector-polyline',
  testPlan: 'mdi-test-tube',
  design: 'mdi-palette-outline',
  slackTriage: 'mdi-slack',
}

const AGENT_ACCENTS: Record<AgentType, string> = {
  triage: 'rgb(120, 180, 255)',
  bud: 'rgb(120, 220, 150)',
  status: 'rgb(180, 200, 120)',
  standup: 'rgb(220, 180, 100)',
  learning: 'rgb(180, 140, 220)',
  bugLinker: 'rgb(240, 130, 130)',
  reassignment: 'rgb(220, 180, 100)',
  skill: 'rgb(100, 200, 180)',
  techPlan: 'rgb(140, 180, 240)',
  testPlan: 'rgb(160, 220, 160)',
  design: 'rgb(230, 150, 220)',
  slackTriage: 'rgb(180, 140, 220)',
}

const AGENT_BLURBS: Record<AgentType, string> = {
  triage: 'Classifies inbound items into BUDs vs noise',
  bud: 'Writes the PRD when a BUD is opened',
  status: 'Surfaces DevOps and infra signals',
  standup: 'Generates the daily team digest',
  learning: 'Captures retrospective learnings',
  bugLinker: 'Matches incoming bugs to existing BUDs',
  reassignment: 'Suggests new owners when assignments stall',
  skill: 'Reviews code for the code-review stage',
  techPlan: 'Authors the technical architecture',
  testPlan: 'Designs test plans and QA cases',
  design: 'Produces visual designs from the design system',
  slackTriage: 'Triages Slack messages into actions',
}

function agentIcon(at: AgentType): string {
  return AGENT_ICONS[at] ?? 'mdi-robot-outline'
}

function agentAccent(at: AgentType): string {
  return AGENT_ACCENTS[at] ?? 'rgb(46, 125, 50)'
}

function agentBlurb(at: AgentType): string {
  return AGENT_BLURBS[at] ?? ''
}

// Stable display order of agent types — matches the visible BUD lifecycle
// flow first (bud → design → tech_plan → test_plan → skill review), then the
// non-stage agents (triage, standup, etc.) below.
const AGENT_ORDER: AgentType[] = [
  'bud', 'design', 'techPlan', 'testPlan', 'skill',
  'triage', 'bugLinker', 'reassignment', 'standup',
  'learning', 'status', 'slackTriage',
]

interface AgentGroup {
  agentType: AgentType
  skills: AgentSkill[]
}

const filteredGroups = computed<AgentGroup[]>(() => {
  const q = search.value.trim().toLowerCase()
  const grouped = new Map<AgentType, AgentSkill[]>()
  for (const s of store.skills) {
    if (filterMode.value === 'custom' && !s.isCustom) continue
    if (filterMode.value === 'modified' && !s.isCustomized) continue
    if (q) {
      const hay = `${s.name} ${s.description} ${s.skillSlug}`.toLowerCase()
      if (!hay.includes(q)) continue
    }
    const list = grouped.get(s.agentType) ?? []
    list.push(s)
    grouped.set(s.agentType, list)
  }
  const ordered: AgentGroup[] = []
  for (const at of AGENT_ORDER) {
    const skills = grouped.get(at)
    if (skills && skills.length > 0) {
      ordered.push({
        agentType: at,
        skills: skills.sort((a, b) => {
          if (a.isCustom !== b.isCustom) return a.isCustom ? 1 : -1
          if (a.isDefault !== b.isDefault) return a.isDefault ? -1 : 1
          return a.name.localeCompare(b.name)
        }),
      })
    }
  }
  return ordered
})

const modelOptions = [
  { title: 'Default', value: '' },
  { title: 'Sonnet', value: 'sonnet' },
  { title: 'Opus', value: 'opus' },
  { title: 'Haiku', value: 'haiku' },
]

const iterationModelOptions = [
  { title: 'Same as model', value: '' },
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

function openCreateForAgent(at: AgentType): void {
  createForAgent.value = at
  showCreateDialog.value = true
}

function onCustomCreated(): void {
  showCreateDialog.value = false
  createForAgent.value = null
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

/* ── Header ──────────────────────────────────────────────────── */

.page-header {
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 2;
  background: rgb(var(--v-theme-background));
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  backdrop-filter: blur(8px);
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
  margin: 0;
  color: rgb(var(--v-theme-on-surface));
}

.page-subtitle {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  max-width: 560px;
  line-height: 1.5;
}

.search-input {
  max-width: 420px;
  flex: 1;
}

.search-input :deep(.v-field) {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 10px;
}

.filter-chips :deep(.v-chip) {
  text-transform: none;
  font-weight: 500;
}

.filter-chip-selected {
  background-color: rgba(var(--v-theme-primary), 0.18) !important;
  color: rgb(var(--v-theme-primary)) !important;
}

/* ── Content ─────────────────────────────────────────────────── */

.page-content {
  flex: 1;
  min-height: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 72px 0;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.empty-state .v-icon { opacity: 0.4; margin-bottom: 4px; }
.empty-title { font-size: 15px; font-weight: 500; color: rgba(var(--v-theme-on-surface), 0.7); }
.empty-sub { font-size: 13px; }

/* ── Agent group ─────────────────────────────────────────────── */

.agent-group {
  display: flex;
  flex-direction: column;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 4px 12px;
}

.group-icon-wrap {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent);
}

.group-icon-wrap .v-icon {
  color: var(--accent);
}

.group-meta { flex: 1; min-width: 0; }
.group-title {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0;
  color: rgb(var(--v-theme-on-surface));
}
.group-sub {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.group-count {
  font-variant-numeric: tabular-nums;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
}

/* ── Skill list ──────────────────────────────────────────────── */

.skill-list {
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.6);
  overflow: hidden;
}

.skill-row + .skill-row .skill-summary {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.skill-row.is-open {
  background: rgba(var(--v-theme-on-surface), 0.025);
}

.skill-summary {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  width: 100%;
  box-sizing: border-box;
  transition: background 120ms ease;
}

.skill-summary:hover { background: rgba(var(--v-theme-on-surface), 0.04); }
.skill-summary:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.45);
  outline-offset: -2px;
}

.skill-chevron { color: rgba(var(--v-theme-on-surface), 0.45); flex-shrink: 0; }

.skill-headline { flex: 1; min-width: 0; }

.skill-name-row { display: flex; align-items: center; flex-wrap: wrap; }
.skill-name {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: rgb(var(--v-theme-on-surface));
}
.skill-desc {
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-top: 2px;
  line-height: 1.45;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 720px;
}

.skill-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.skill-meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.7);
  background: rgba(var(--v-theme-on-surface), 0.06);
  text-transform: lowercase;
}

.skill-slug {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
}

/* ── Editor ──────────────────────────────────────────────────── */

.skill-editor {
  padding: 14px 18px 18px;
}

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

.prompt-editor :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.65;
}

.prompt-editor :deep(.v-field) {
  background: rgba(0, 0, 0, 0.18);
}

.preview-content {
  max-height: 540px;
  overflow-y: auto;
  padding: 16px 18px;
  background: rgba(0, 0, 0, 0.18);
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
  background: rgba(0, 0, 0, 0.32);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 6px;
  padding: 12px 16px;
  margin: 10px 0;
  overflow-x: auto;
}
.preview-content :deep(pre code) { background: none; padding: 0; }
.preview-content :deep(ul),
.preview-content :deep(ol) { padding-left: 20px; margin: 8px 0; }

.editor-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.05);
}

/* ── Add-skill button (per group) ────────────────────────────── */

.skill-add {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.55);
  border-top: 1px dashed rgba(var(--v-theme-on-surface), 0.1);
  transition: background 120ms ease, color 120ms ease;
}
.skill-add:hover {
  background: rgba(var(--v-theme-primary), 0.06);
  color: rgb(var(--v-theme-primary));
}

/* ── Confirm dialogs ─────────────────────────────────────────── */

.confirm-card { padding: 24px; }
.confirm-icon {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}
.confirm-icon-warn {
  background: rgba(var(--v-theme-warning), 0.16);
  color: rgb(var(--v-theme-warning));
}
.confirm-icon-err {
  background: rgba(var(--v-theme-error), 0.16);
  color: rgb(var(--v-theme-error));
}
.confirm-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 6px;
  color: rgb(var(--v-theme-on-surface));
}
.confirm-body {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  line-height: 1.55;
  margin: 0 0 18px;
}
.confirm-actions { display: flex; justify-content: flex-end; gap: 8px; }
</style>
