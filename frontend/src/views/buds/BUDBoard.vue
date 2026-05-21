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
  <div class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="text-h5 font-weight-bold">BUD Board</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ budStore.buds.length }} document{{ budStore.buds.length !== 1 ? 's' : '' }}
        </div>
      </div>
      <div class="d-flex align-center ga-2">
        <!-- Customize lifecycle stages — same permission gate as the
             settings route. Visible to users who can actually change
             the UAT toggle / framework; hidden for plain viewers. -->
        <v-tooltip v-if="canViewQAAutomation" text="Customize QA framework & lifecycle stages" location="bottom">
          <template #activator="{ props: tipProps }">
            <v-btn
              v-bind="tipProps"
              icon="mdi-cog-outline"
              variant="text"
              size="small"
              :to="{ name: 'settings-qa-automation' }"
            />
          </template>
        </v-tooltip>
        <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
          New BUD
        </v-btn>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="budStore.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error -->
    <v-alert v-else-if="budStore.error" type="error" variant="tonal" class="mb-4">
      {{ budStore.error }}
      <template #append>
        <v-btn variant="text" size="small" @click="budStore.fetchBUDs()">Retry</v-btn>
      </template>
    </v-alert>

    <!-- Empty state -->
    <v-card
      v-else-if="budStore.buds.length === 0"
      class="pa-12 text-center"
      color="surface"
    >
      <v-icon icon="mdi-seed-outline" size="64" class="text-medium-emphasis mb-4" />
      <div class="text-h6 mb-2">No BUDs yet</div>
      <div class="text-body-2 text-medium-emphasis mb-6">
        Create your first Business Understanding Document to plant a seed.
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        Create BUD
      </v-btn>
    </v-card>

    <!-- Kanban Board -->
    <div v-else class="board-container">
      <div class="board-scroll">
        <div
          v-for="status in boardColumns"
          :key="status"
          class="board-column"
        >
          <!-- Column header -->
          <div class="column-header d-flex align-center justify-space-between pa-3 mb-2">
            <div class="d-flex align-center ga-2">
              <v-chip
                :color="BUD_STATUS_COLORS[status]"
                size="x-small"
                variant="flat"
                label
              >
                {{ budStore.budsByStatus[status]?.length || 0 }}
              </v-chip>
              <span class="text-body-2 font-weight-medium">{{ BUD_STATUS_LABELS[status] }}</span>
            </div>
          </div>

          <!-- Cards -->
          <div class="column-cards">
            <v-card
              v-for="bud in budStore.budsByStatus[status]"
              :key="bud.id"
              class="bud-card pa-4 mb-2 cursor-pointer"
              color="surface"
              @click="openBUD(bud.id)"
            >
              <!-- Row 1: BUD number + complexity dots -->
              <div class="d-flex align-center justify-space-between mb-1">
                <div class="text-caption text-medium-emphasis">
                  BUD-{{ String(bud.bud_number).padStart(3, '0') }}
                </div>
                <div v-if="bud.complexity" class="d-flex ga-1">
                  <span
                    v-for="i in 5"
                    :key="i"
                    class="complexity-dot"
                    :class="i <= (bud.complexity ?? 0) ? 'dot-filled' : 'dot-empty'"
                  />
                </div>
              </div>

              <!-- Row 2: Title + bug badge -->
              <div class="d-flex align-center mb-2">
                <div class="text-body-2 font-weight-medium flex-grow-1 text-truncate">{{ bud.title }}</div>
                <v-chip
                  v-if="bud.open_bug_count > 0"
                  size="x-small"
                  variant="tonal"
                  color="error"
                  prepend-icon="mdi-bug-outline"
                  class="ml-2 flex-shrink-0"
                  @click.stop="$router.push(`/bugs?budId=${bud.id}`)"
                >
                  {{ bud.open_bug_count }}
                </v-chip>
              </div>

              <!-- Row 3: Phase deadline + go-live (only if estimates exist) -->
              <div v-if="bud.current_phase_deadline" class="text-caption mb-1" :class="deadlineColor(bud.current_phase_deadline)">
                ▸ Phase: {{ formatDate(bud.current_phase_deadline) }}
              </div>
              <div v-if="bud.status === 'closed'" class="text-caption text-success mb-2">
                ▸ Released: {{ formatDate(bud.updated_at) }}
              </div>
              <div v-else-if="bud.status === 'discarded'" class="text-caption text-error mb-2">
                ▸ Discarded: {{ formatDate(bud.updated_at) }}
              </div>
              <div v-else-if="bud.prod_p70_date" class="text-caption text-medium-emphasis mb-2">
                ▸ Live: {{ formatDate(bud.prod_p70_date) }} (70%)
              </div>

              <!-- Row 4: Progress bar + date/avatar -->
              <v-progress-linear
                :model-value="phaseProgress(bud.status)"
                height="3"
                rounded
                color="primary"
                bg-color="surface-variant"
                class="mb-2"
              />
              <div class="d-flex align-center justify-space-between">
                <div class="text-caption text-medium-emphasis">
                  {{ formatDate(bud.updated_at) }}
                </div>
                <v-avatar
                  v-if="bud.assignee_name"
                  size="22"
                  color="primary"
                  variant="tonal"
                  :title="bud.assignee_name"
                >
                  <span class="text-caption" style="font-size: 10px;">{{ initials(bud.assignee_name) }}</span>
                </v-avatar>
              </div>
            </v-card>

            <div
              v-if="!budStore.budsByStatus[status]?.length"
              class="text-caption text-medium-emphasis text-center pa-4"
              style="opacity: 0.4;"
            >
              No items
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create BUD Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="560">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 font-weight-bold mb-4">New BUD</div>
        <v-text-field
          v-model="newTitle"
          label="Title"
          placeholder="e.g. Payment retry logic"
          autofocus
          class="mb-3"
          :rules="[v => !!v?.trim() || 'Title is required']"
          @keyup.enter="createBUD"
        />
        <v-textarea
          v-model="newContent"
          label="Description (optional)"
          placeholder="Brief description or requirements..."
          rows="4"
          variant="outlined"
        />

        <!-- Advanced Settings: per-stage skill picker -->
        <v-expansion-panels v-model="advancedPanel" variant="accordion" class="mt-3">
          <v-expansion-panel value="advanced">
            <v-expansion-panel-title>
              <v-icon icon="mdi-tune-variant" size="20" class="mr-2" />
              Advanced settings
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <!-- Per-phase auto-generation. All phases default ON —
                   our agents run by default for a new BUD; toggle any
                   phase OFF to drive it yourself (typically via your
                   local AI through Settings → MCP Connect). The
                   per-stage skill picker only matters for phases that
                   are still opted in. -->
              <div class="text-caption text-medium-emphasis mb-3">
                Pick which phases our AI agent should auto-run. Anything
                left off, you drive yourself via the section editors
                (typically using your local AI through
                <strong>Settings → MCP Connect</strong>).
              </div>
              <div class="d-flex flex-column ga-2 mb-4">
                <v-switch
                  v-for="stage in advancedStages"
                  :key="`gen-${stage.value}`"
                  v-model="autoGeneratePhases[stage.value]"
                  :label="`Auto-generate ${stage.label}`"
                  color="primary"
                  density="compact"
                  hide-details
                  inset
                />
              </div>
              <v-progress-circular
                v-if="skillsStore.loading"
                indeterminate
                size="20"
                class="my-3"
              />
              <div v-else class="d-flex flex-column ga-3">
                <!-- Per-stage skill picker. Only enabled for phases the
                     user explicitly opted in to via the switches above.
                     Picking a skill for a phase that's off would have
                     no runtime effect, so we dim/disable until opt-in. -->
                <div
                  v-for="stage in advancedStages"
                  :key="stage.value"
                  class="d-flex align-center ga-2"
                  :style="{ opacity: autoGeneratePhases[stage.value] ? 1 : 0.4 }"
                >
                  <span class="stage-label">{{ stage.label }}</span>
                  <v-select
                    v-model="stageSkillPicks[stage.value]"
                    :items="skillsForStage(stage.agentType)"
                    item-title="label"
                    item-value="id"
                    density="compact"
                    variant="outlined"
                    hide-details
                    :disabled="!autoGeneratePhases[stage.value]"
                    class="flex-grow-1"
                  />
                </div>
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>

        <v-card-actions class="pa-0 mt-4">
          <v-spacer />
          <v-btn variant="text" @click="showCreateDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="creating"
            :disabled="!newTitle.trim()"
            @click="createBUD"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { useAgentSkillsStore, type AgentType, type AgentSkill } from '@/stores/agentSkills'
import { BUD_STATUS_LABELS, BUD_STATUS_COLORS } from '@/types'
import type { BUDStatus } from '@/types'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import { usePermissions } from '@/composables/usePermissions'

const router = useRouter()
const budStore = useBUDStore()
const skillsStore = useAgentSkillsStore()

const showCreateDialog = ref(false)
const newTitle = ref('')
const newContent = ref('')
const creating = ref(false)
const advancedPanel = ref<string | null>(null)
const stageSkillPicks = ref<Record<string, string | null>>({})
// Per-phase auto-generate switches. ALL FALSE by default — fresh BUDs
// ship in External-LLM mode and the user opts in per phase. Initialised
// once below in prefillStageDefaults / closeAndReset rather than as a
// const literal so future stage additions only need a single edit on
// ``advancedStages``.
const autoGeneratePhases = ref<Record<string, boolean>>({})

// Single source of truth for which stages get a dropdown — mirrors
// BUD_STAGE_AGENT_TYPE in backend/app/agents/skill_mapping.py. If a new
// stage gets an agent on the backend, add it here too.
interface StageConfig { value: BUDStatus; label: string; agentType: AgentType }
const advancedStages: StageConfig[] = [
  { value: 'bud' as BUDStatus, label: 'PRD writer', agentType: 'bud' },
  { value: 'design' as BUDStatus, label: 'Design', agentType: 'design' },
  { value: 'tech_arch' as BUDStatus, label: 'Tech plan', agentType: 'techPlan' },
  { value: 'testing' as BUDStatus, label: 'Test plan', agentType: 'testPlan' },
]

interface StageSkillOption { id: string; label: string; isDefault: boolean }

function skillsForStage(agentType: AgentType): StageSkillOption[] {
  return skillsStore.skills
    .filter((s): s is AgentSkill & { id: string } => s.agentType === agentType && s.id !== null)
    .map(s => ({
      id: s.id,
      label: s.isDefault ? `${s.name} · default` : s.name,
      isDefault: s.isDefault,
    }))
}

function defaultSkillIdForAgent(agentType: AgentType): string | null {
  const def = skillsStore.skills.find(s => s.agentType === agentType && s.isDefault)
  return def?.id ?? null
}

function prefillStageDefaults(): void {
  for (const stage of advancedStages) {
    stageSkillPicks.value[stage.value] = defaultSkillIdForAgent(stage.agentType)
    // Default each phase to ON for new BUDs — user feedback was that
    // the previous all-skip default required clicking through Advanced
    // settings just to get the in-flight default behaviour. Users who
    // want External-LLM mode can still flip individual switches OFF
    // before creating, or change them later via the AI skills dialog.
    if (autoGeneratePhases.value[stage.value] === undefined) {
      autoGeneratePhases.value[stage.value] = true
    }
  }
}

// Lazy-load skills the first time the dialog opens, then pre-fill each
// stage dropdown with that agent type's current default — gives users a
// clear "what would run if I change nothing" signal instead of an empty
// "Skill" placeholder.
watch(showCreateDialog, async open => {
  if (!open) return
  if (skillsStore.skills.length === 0 && !skillsStore.loading) {
    await skillsStore.fetchSkills()
  }
  prefillStageDefaults()
})

// If the skills load AFTER the dialog opened (slow network), re-prefill.
watch(
  () => skillsStore.skills.length,
  () => {
    if (showCreateDialog.value) prefillStageDefaults()
  },
)

onMounted(() => {
  budStore.fetchBUDs()
})

function openBUD(id: string): void {
  router.push(`/buds/${id}`)
}

async function createBUD(): Promise<void> {
  if (!newTitle.value.trim()) return
  creating.value = true
  // Only persist overrides where the user picked a NON-default skill.
  // Matching-the-default picks are dropped so the BUD continues to
  // follow whatever the org admin marks as default later, rather than
  // being pinned to today's default skill_id.
  const overrides: Record<string, string> = {}
  for (const stage of advancedStages) {
    const picked = stageSkillPicks.value[stage.value]
    if (!picked) continue
    if (picked === defaultSkillIdForAgent(stage.agentType)) continue
    overrides[stage.value] = picked
  }
  // Snapshot the switches by value so a later reset doesn't mutate the
  // payload object reactively.
  const phases: Record<string, boolean> = {}
  for (const stage of advancedStages) {
    phases[stage.value] = !!autoGeneratePhases.value[stage.value]
  }
  const bud = await budStore.createBUD(
    newTitle.value.trim(),
    newContent.value.trim() || undefined,
    Object.keys(overrides).length > 0 ? overrides : undefined,
    phases,
  )
  creating.value = false
  if (bud) {
    showCreateDialog.value = false
    newTitle.value = ''
    newContent.value = ''
    stageSkillPicks.value = {}
    advancedPanel.value = null
    autoGeneratePhases.value = {}
    router.push(`/buds/${bud.id}`)
  }
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}

// Phase order filtered by org settings (e.g. UAT may be disabled). The
// kanban columns and progress-bar denominator both use this so the board
// reacts when the org toggles UAT off, without a page reload.
const { phaseOrder } = usePhaseOrder()
const { canViewQAAutomation } = usePermissions()
const boardColumns = computed<BUDStatus[]>(() =>
  phaseOrder.value.filter(s => s !== 'discarded'),
)
const activePhaseCount = computed<number>(
  () => phaseOrder.value.filter(s => s !== 'discarded' && s !== 'closed').length,
)

function phaseProgress(status: BUDStatus): number {
  // Use the filtered phaseOrder for both numerator and denominator so the
  // progress bar is consistent regardless of whether UAT is enabled.
  const idx = phaseOrder.value.indexOf(status)
  return idx >= 0 ? Math.min(100, ((idx + 1) / activePhaseCount.value) * 100) : 0
}

function deadlineColor(deadline: string): string {
  const days = (new Date(deadline).getTime() - Date.now()) / 86400000
  if (days < 0) return 'text-error'
  if (days < 2) return 'text-warning'
  return 'text-medium-emphasis'
}
</script>

<style scoped>
.board-container {
  overflow-x: auto;
}

.board-scroll {
  display: flex;
  gap: 12px;
  min-width: max-content;
  padding-bottom: 8px;
}

.board-column {
  width: 260px;
  min-width: 260px;
  flex-shrink: 0;
}

.column-header {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
}

.column-cards {
  min-height: 100px;
}

.bud-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.15s ease;
}

.bud-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.4);
}

.complexity-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.dot-filled {
  background: rgb(var(--v-theme-primary));
}

.dot-empty {
  background: rgba(255, 255, 255, 0.12);
}

.stage-label {
  width: 110px;
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
</style>
