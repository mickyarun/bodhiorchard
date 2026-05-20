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
  <v-dialog
    :model-value="modelValue"
    max-width="580"
    persistent
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="dialog-card">
      <header class="dialog-header">
        <div class="dialog-icon">
          <v-icon icon="mdi-tune-variant" size="20" />
        </div>
        <div class="dialog-title-wrap">
          <h3 class="dialog-title">AI skills for this BUD</h3>
          <div class="dialog-sub">
            Pick which skill runs at each stage. Leave "default" to follow
            the org-wide setting in <em>Settings → Agent Prompts</em>.
          </div>
        </div>
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          density="comfortable"
          @click="close"
        />
      </header>

      <v-divider />

      <div class="dialog-body">
        <v-alert
          v-if="errorMessage"
          type="error"
          variant="tonal"
          density="compact"
          class="mb-3"
        >
          {{ errorMessage }}
        </v-alert>

        <div v-if="loading" class="d-flex justify-center py-6">
          <v-progress-circular indeterminate size="22" color="primary" />
        </div>

        <div v-else class="stage-list">
          <div class="stage-list-hint text-caption text-medium-emphasis">
            Toggle a phase ON to let our agent auto-run when the BUD
            enters that stage. Toggle OFF to drive that phase yourself
            (typically via your local AI through
            <strong>Settings → MCP Connect</strong>). The skill picker
            only matters for phases that are ON.
          </div>
          <div
            v-for="stage in advancedStages"
            :key="stage.value"
            class="stage-row"
          >
            <v-switch
              v-model="autoPhases[stage.value]"
              color="primary"
              density="compact"
              hide-details
              inset
              class="stage-switch"
              :aria-label="`Auto-generate ${stage.label}`"
            />
            <div class="stage-label-wrap">
              <span class="stage-label">{{ stage.label }}</span>
              <span class="stage-agent">{{ agentTypeName(stage.agentType) }}</span>
            </div>
            <v-select
              v-model="picks[stage.value]"
              :items="skillsForStage(stage.agentType)"
              item-title="label"
              item-value="id"
              density="compact"
              variant="outlined"
              hide-details
              :disabled="!autoPhases[stage.value]"
              class="stage-select"
            />
          </div>
        </div>
      </div>

      <v-divider />

      <footer class="dialog-footer">
        <v-spacer />
        <v-btn variant="text" class="text-none" @click="close">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          class="text-none"
          :loading="saving"
          @click="save"
        >
          Save
        </v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import api from '@/services/api'
import {
  AGENT_TYPE_LABELS,
  useAgentSkillsStore,
  type AgentType,
  type AgentSkill,
} from '@/stores/agentSkills'

interface Props {
  modelValue: boolean
  budId: string
  // Current auto_generate_phases map straight from the BUD row. Loaded
  // into the local ``autoPhases`` ref each time the dialog opens so the
  // switches reflect whatever the backend has stored, including any
  // previous edits made from this same dialog earlier in the session.
  autoGeneratePhases?: Record<string, boolean> | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
}>()

const skillsStore = useAgentSkillsStore()
const loading = ref(false)
const saving = ref(false)
const errorMessage = ref<string | null>(null)
// Map of stage → either a real skill UUID or null (meaning "use org default").
const picks = ref<Record<string, string | null>>({})
// Per-phase auto-generate flags. Missing key in the incoming
// autoGeneratePhases prop = false (= phase off) — matches the backend's
// ``phases.get(stage, False)`` semantic so the UI never shows a phase
// as enabled when the server treats it as off.
const autoPhases = ref<Record<string, boolean>>({})

interface StageConfig { value: string; label: string; agentType: AgentType }
const advancedStages: StageConfig[] = [
  { value: 'bud', label: 'PRD writer', agentType: 'bud' },
  { value: 'design', label: 'Design', agentType: 'design' },
  { value: 'tech_arch', label: 'Tech plan', agentType: 'techPlan' },
  { value: 'testing', label: 'Test plan', agentType: 'testPlan' },
]

interface StageSkillOption { id: string; label: string }

function skillsForStage(agentType: AgentType): StageSkillOption[] {
  return skillsStore.skills
    .filter((s): s is AgentSkill & { id: string } =>
      s.agentType === agentType && s.id !== null,
    )
    .map(s => ({
      id: s.id,
      label: s.isDefault ? `${s.name} · default` : s.name,
    }))
}

function defaultSkillIdForAgent(agentType: AgentType): string | null {
  const def = skillsStore.skills.find(s => s.agentType === agentType && s.isDefault)
  return def?.id ?? null
}

function agentTypeName(agentType: AgentType): string {
  return AGENT_TYPE_LABELS[agentType] ?? agentType
}

interface ApiError {
  response?: { data?: { detail?: string } }
}

function extractError(err: unknown, fallback: string): string {
  const e = err as ApiError
  return e?.response?.data?.detail ?? fallback
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    if (skillsStore.skills.length === 0) await skillsStore.fetchSkills()
    // Pre-fill each stage with its current override (if any), else default.
    const { data } = await api.get<Record<string, string>>(
      `/v1/buds/${props.budId}/stage-skill-overrides`,
    )
    const nextPicks: Record<string, string | null> = {}
    const nextPhases: Record<string, boolean> = {}
    const incomingPhases = props.autoGeneratePhases ?? {}
    for (const stage of advancedStages) {
      nextPicks[stage.value] = data[stage.value] ?? defaultSkillIdForAgent(stage.agentType)
      nextPhases[stage.value] = !!incomingPhases[stage.value]
    }
    picks.value = nextPicks
    autoPhases.value = nextPhases
  } catch (err) {
    errorMessage.value = extractError(err, 'Failed to load BUD skill settings.')
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  saving.value = true
  errorMessage.value = null
  try {
    // Two writes here are intentional: stage-skill overrides have their
    // own validated PUT endpoint (rejects skill_id / agent_type
    // mismatches with 400), while auto_generate_phases goes through the
    // generic BUD PATCH. Fire skills first; if it 400s we don't want a
    // half-applied state where phases changed but skills didn't.
    const overridesBody: Record<string, string> = {}
    for (const stage of advancedStages) {
      const picked = picks.value[stage.value]
      if (!picked) continue
      if (picked === defaultSkillIdForAgent(stage.agentType)) continue
      overridesBody[stage.value] = picked
    }
    await api.put(`/v1/buds/${props.budId}/stage-skill-overrides`, overridesBody)
    // Send the full normalised map (every stage key with a boolean) so
    // the backend's setattr replace is unambiguous — never partial.
    const phasesBody: Record<string, boolean> = {}
    for (const stage of advancedStages) {
      phasesBody[stage.value] = !!autoPhases.value[stage.value]
    }
    await api.patch(`/v1/buds/${props.budId}`, { auto_generate_phases: phasesBody })
    emit('saved')
    close()
  } catch (err) {
    errorMessage.value = extractError(err, 'Failed to save settings.')
  } finally {
    saving.value = false
  }
}

function close(): void {
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  open => {
    if (open) load()
  },
)
</script>

<style scoped>
.dialog-card {
  display: flex;
  flex-direction: column;
  background: rgb(var(--v-theme-surface));
  border-radius: 14px;
  overflow: hidden;
  max-height: 90vh;
}

.dialog-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
}

.dialog-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(var(--v-theme-primary), 0.14);
  color: rgb(var(--v-theme-primary));
  display: flex;
  align-items: center;
  justify-content: center;
}
.dialog-icon .v-icon { color: rgb(var(--v-theme-primary)); }

.dialog-title-wrap { flex: 1; min-width: 0; }
.dialog-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 2px;
  color: rgb(var(--v-theme-on-surface));
}
.dialog-sub {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  line-height: 1.45;
}

.dialog-body {
  padding: 16px 18px;
  overflow-y: auto;
  flex: 1;
}

.stage-list { display: flex; flex-direction: column; gap: 10px; }

.stage-row {
  display: grid;
  grid-template-columns: 150px 1fr;
  align-items: center;
  gap: 14px;
}

.stage-label-wrap { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.stage-label {
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
}
.stage-agent {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.5);
}

.stage-select :deep(.v-field--variant-outlined .v-field__input) {
  min-height: 36px;
  padding-top: 4px;
  padding-bottom: 4px;
}

.dialog-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
}
</style>
