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
          {{ filteredCount }} of {{ budStore.buds.length }} document{{ budStore.buds.length !== 1 ? 's' : '' }}
        </div>
      </div>
      <div class="d-flex align-center ga-2 board-filters">
        <v-text-field
          v-model="nameFilter"
          placeholder="Filter by title or BUD-###"
          prepend-inner-icon="mdi-magnify"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          clearable
          single-line
          class="board-filter-search"
        />
        <v-select
          v-model="assigneeFilter"
          :items="assigneeOptions"
          item-title="label"
          item-value="value"
          placeholder="All assignees"
          prepend-inner-icon="mdi-account-outline"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          clearable
          single-line
          class="board-filter-assignee"
        />
        <v-select
          v-model="priorityFilter"
          :items="priorityFilterOptions"
          item-title="label"
          item-value="value"
          placeholder="All priorities"
          prepend-inner-icon="mdi-flag-outline"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          clearable
          single-line
          class="board-filter-priority"
        />
        <v-tooltip text="Sort cards by priority (P0 first) within each column" location="bottom">
          <template #activator="{ props: tipProps }">
            <v-btn
              v-bind="tipProps"
              :icon="sortByPriority ? 'mdi-sort-descending' : 'mdi-sort-variant'"
              variant="text"
              size="small"
              :color="sortByPriority ? 'primary' : undefined"
              @click="sortByPriority = !sortByPriority"
            />
          </template>
        </v-tooltip>
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

    <!-- Yield-offer notices addressed to the current user (or every
         org-wide offer if the viewer has team:manage). Renders nothing
         when there are no pending offers. -->
    <YieldOfferNotice />

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
                {{ filteredBudsByStatus[status]?.length || 0 }}
              </v-chip>
              <span class="text-body-2 font-weight-medium">{{ BUD_STATUS_LABELS[status] }}</span>
            </div>
          </div>

          <!-- Cards -->
          <div class="column-cards">
            <v-card
              v-for="bud in filteredBudsByStatus[status]"
              :key="bud.id"
              class="bud-card pa-4 mb-2 cursor-pointer"
              color="surface"
              @click="openBUD(bud.id)"
            >
              <!-- Row 1: BUD number + priority chip + complexity dots -->
              <div class="d-flex align-center justify-space-between mb-1">
                <div class="d-flex align-center ga-2">
                  <div class="text-caption text-medium-emphasis">
                    BUD-{{ String(bud.bud_number).padStart(3, '0') }}
                  </div>
                  <v-chip
                    size="x-small"
                    variant="tonal"
                    :color="priorityColor(bud.priority)"
                    :title="`Priority ${bud.priority}`"
                    label
                  >
                    {{ bud.priority }}
                  </v-chip>
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
              v-if="!filteredBudsByStatus[status]?.length"
              class="text-caption text-medium-emphasis text-center pa-4"
              style="opacity: 0.4;"
            >
              {{ nameFilter ? 'No matches' : 'No items' }}
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

        <!-- Priority: defaults to P2 (normal). Drives the assignment
             scorer (lower-priority work is preferred for displacement)
             and the yield-offer flow. -->
        <div class="d-flex align-center ga-3 mb-3">
          <div class="text-body-2 text-medium-emphasis" style="min-width: 70px;">Priority</div>
          <AppPillToggle v-model="newPriority" :options="PRIORITY_OPTIONS" size="sm" />
        </div>

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
              <AppCallout
                v-if="autoGeneratePhases.closed === false"
                variant="warning"
                eyebrow="Learning recap disabled"
                icon="mdi-alert-outline"
                class="mb-4"
              >
                Without the post-close recap, this BUD's per-phase actuals
                still feed the velocity rollup that powers future
                estimates — but you lose the written retrospective and
                the trend signal that recap embeddings provide to similar
                BUDs. Leave this on unless you're explicitly using your
                own LLM workflow for retrospectives.
              </AppCallout>
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
import AppCallout from '@/components/common/AppCallout.vue'
import { useBUDStore } from '@/stores/bud'
import { useAgentSkillsStore, type AgentType, type AgentSkill } from '@/stores/agentSkills'
import { useSettingsStore } from '@/stores/settings'
import { BUD_STATUS_LABELS, BUD_STATUS_COLORS, BUD_PRIORITIES } from '@/types'
import type { BUDStatus, BUDPriority } from '@/types'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import { usePermissions } from '@/composables/usePermissions'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import YieldOfferNotice from '@/components/buds/YieldOfferNotice.vue'

// Theme-token color for each priority. Used by the chip on each card
// AND by the filter / sort surface so the visual contract is identical
// across the board.
const PRIORITY_COLORS: Record<BUDPriority, string> = {
  P0: 'error',
  P1: 'warning',
  P2: 'on-surface-variant',
  P3: 'on-surface-variant',
}
const PRIORITY_WEIGHTS: Record<BUDPriority, number> = { P0: 0, P1: 1, P2: 2, P3: 3 }
const PRIORITY_OPTIONS = BUD_PRIORITIES.map(p => ({ label: p, value: p }))

const router = useRouter()
const budStore = useBUDStore()
const skillsStore = useAgentSkillsStore()
const settingsStore = useSettingsStore()

const nameFilter = ref('')
// Sentinel value (string, not null) for the "Unassigned" option — v-select's
// `clearable` resets to null, which we treat as "no filter".
const UNASSIGNED = '__unassigned__'
const assigneeFilter = ref<string | null>(null)
const priorityFilter = ref<BUDPriority | null>(null)
const sortByPriority = ref(false)

// Dropdown options derived from the currently-loaded buds so we only show
// assignees that actually exist on the board. "Unassigned" is appended
// only if at least one BUD has no assignee.
const assigneeOptions = computed(() => {
  const seen = new Map<string, string>()
  let hasUnassigned = false
  for (const bud of budStore.buds) {
    if (bud.assignee_id && bud.assignee_name) seen.set(bud.assignee_id, bud.assignee_name)
    else hasUnassigned = true
  }
  const opts = [...seen.entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label))
  if (hasUnassigned) opts.push({ value: UNASSIGNED, label: 'Unassigned' })
  return opts
})

const priorityFilterOptions = BUD_PRIORITIES.map(p => ({ label: p, value: p }))

// Filter buds by title (case-insensitive substring) OR by BUD reference
// like "BUD-014" / "014" / "14", AND by assignee. Applied after the store's
// status grouping so kanban columns stay intact and the filter is purely
// visual.
const filteredBudsByStatus = computed<Record<string, typeof budStore.buds>>(() => {
  const q = nameFilter.value?.trim().toLowerCase() ?? ''
  const assignee = assigneeFilter.value
  const priority = priorityFilter.value
  const sort = sortByPriority.value
  const grouped = budStore.budsByStatus
  if (!q && !assignee && !priority && !sort) return grouped
  const numericQ = q.replace(/^bud-?/, '').replace(/^0+/, '')
  const out: Record<string, typeof budStore.buds> = {}
  for (const status of Object.keys(grouped)) {
    const filtered = grouped[status].filter((bud) => {
      if (assignee === UNASSIGNED && bud.assignee_id) return false
      if (assignee && assignee !== UNASSIGNED && bud.assignee_id !== assignee) return false
      if (priority && bud.priority !== priority) return false
      if (!q) return true
      if (bud.title?.toLowerCase().includes(q)) return true
      const num = String(bud.bud_number)
      return numericQ !== '' && num.includes(numericQ)
    })
    out[status] = sort
      ? [...filtered].sort((a, b) => PRIORITY_WEIGHTS[a.priority] - PRIORITY_WEIGHTS[b.priority])
      : filtered
  }
  return out
})

const filteredCount = computed(() =>
  Object.values(filteredBudsByStatus.value).reduce((n, list) => n + list.length, 0),
)

const showCreateDialog = ref(false)
const newTitle = ref('')
const newContent = ref('')
const newPriority = ref<BUDPriority>('P2')
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
  { value: 'closed' as BUDStatus, label: 'Learning recap', agentType: 'learning' },
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
    // Default every phase ON for new BUDs (including the post-close
    // Learning recap). The recap costs a Claude API call per close,
    // but skipping it loses the calibration signal the estimator
    // depends on, so the right default is "on" with a visible warning
    // shown next to the switch when the user flips it off (see the
    // closed-stage warning callout in the template).
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
  // usePhaseOrder() reads budStages.uatEnabled to decide whether the UAT
  // column shows. Without this fetch a cold page load uses the default
  // (UAT enabled) regardless of what the org has saved.
  if (!settingsStore.connectionsLoaded) settingsStore.fetchConnections()
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
    newPriority.value,
  )
  creating.value = false
  if (bud) {
    showCreateDialog.value = false
    newTitle.value = ''
    newContent.value = ''
    newPriority.value = 'P2'
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

function priorityColor(priority: BUDPriority): string {
  return PRIORITY_COLORS[priority]
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

.board-filters :deep(.v-field) {
  background: rgba(255, 255, 255, 0.04);
  border-radius: 8px;
}
.board-filters :deep(.v-field--focused) {
  background: rgba(255, 255, 255, 0.06);
}
.board-filter-search {
  width: 260px;
}
.board-filter-assignee {
  width: 200px;
}

.stage-label {
  width: 110px;
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
</style>
