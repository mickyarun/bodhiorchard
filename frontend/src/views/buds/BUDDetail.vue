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
  <div class="bud-detail-layout">
    <!-- Main content area -->
    <div class="bud-main" :class="{ 'chat-open': chatOpen }">
      <!-- Loading -->
      <div v-if="budStore.loading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <!-- Error -->
      <v-alert v-else-if="budStore.error" type="error" variant="tonal" class="ma-6">
        {{ budStore.error }}
      </v-alert>

      <!-- Content -->
      <template v-else-if="bud">
        <div class="bud-page-content">
          <!-- Header -->
          <BUDHeader
            :bud="bud"
            :status-color="statusColor"
            :status-items="statusItems"
            :is-closed="isClosed"
            :agent-locked="agentLocked"
            :chat-open="chatOpen"
            :chatable="currentSectionChatable"
            @back="router.push('/buds')"
            @update:chat-open="chatOpen = $event"
            @change-assignee="handleAssigneeChange"
            @update-status="updateStatus"
            @delete="confirmDelete = true"
            @save-title="handleSaveTitle"
            @open-skill-settings="skillSettingsOpen = true"
          />

          <!-- External-LLM mode banner. Shown when EVERY phase in
               auto_generate_phases is off (or the dict is empty / null
               — the default for newly-created BUDs). The user drives
               each phase via the section editor, typically using their
               local AI through the remote MCP endpoint. -->
          <v-alert
            v-if="isExternalLlmMode"
            type="info"
            variant="tonal"
            density="compact"
            class="mx-12 mb-3"
            icon="mdi-laptop"
          >
            <div class="d-flex align-center ga-3 flex-wrap">
              <div class="flex-grow-1">
                <strong>External-LLM mode.</strong>
                Stage agents are off for this BUD. Connect your local AI to
                gather context, then paste the finished spec into each
                section editor.
              </div>
              <v-btn
                size="small"
                color="primary"
                variant="flat"
                prepend-icon="mdi-connection"
                :to="{ name: 'settings-mcp-connect' }"
              >
                MCP Connect
              </v-btn>
            </div>
          </v-alert>

          <!-- Workflow banners, approval/reject/reassign dialogs, repo confirmation -->
          <BUDWorkflowActions
            ref="workflowRef"
            :bud="bud"
            :can-approve="canApprove"
            :is-current-assignee="isCurrentAssignee"
            @reload-timeline="loadTimeline(); reloadEstimates()"
          />

          <!-- Status-change banner + guard dialogs + backend-error snackbar.
               Banner renders inline here; dialogs and the snackbar are
               teleported out by Vuetify, so mounting them all from one
               spot has no layout impact. -->
          <BUDStatusDialogs :controller="statusController" />

          <!-- Per-design generating banners. The design phase fans out
               one Claude job per repo, each with its own job_id; a
               task-level cancel can only kill one of them, so we
               surface a banner per design with its own Cancel that
               targets just that repo's run. Rendered alongside the
               task-level banner so both PRD/tech-arch progress and
               in-flight designs are visible during cross-phase work. -->
          <div
            v-for="design in generatingDesigns"
            :key="design.id"
            class="agent-banner mx-12 mb-3"
          >
            <div class="d-flex align-center ga-3">
              <v-icon icon="mdi-palette-outline" size="20" color="primary" />
              <div class="d-flex flex-column agent-banner__text">
                <span class="text-body-2 font-weight-medium">
                  Designer Agent
                </span>
                <span class="text-caption text-medium-emphasis text-truncate">
                  Generating wireframe — {{ design.repo_name || 'default' }}
                </span>
              </div>
              <v-spacer />
              <v-progress-linear
                indeterminate
                color="primary"
                height="3"
                rounded
                class="agent-banner__progress"
              />
              <v-btn
                size="x-small"
                variant="tonal"
                color="warning"
                prepend-icon="mdi-close-circle-outline"
                :loading="cancellingDesignId === design.id"
                @click="cancelDesign(design.id)"
              >
                Cancel
              </v-btn>
            </div>
          </div>

          <!-- Agent generating banner (PRD, tech arch, code review,
               etc.). Suppressed during the design phase because the
               per-design banners above already cover its only signal
               — task.job_id only tracks the first design's worker
               anyway, so the unified label would be misleading. -->
          <div
            v-if="workflowRef?.agentGenerating && bud.status !== 'design'"
            class="agent-banner mx-12 mb-3"
          >
            <div class="d-flex align-center ga-3">
              <v-icon icon="mdi-robot-outline" size="20" color="primary" />
              <div class="d-flex flex-column agent-banner__text">
                <span class="text-body-2 font-weight-medium">
                  {{ workflowRef?.agentName || 'AI Agent' }}
                </span>
                <span class="text-caption text-medium-emphasis text-truncate">
                  {{ workflowRef?.agentStatusMessage || 'Processing...' }}
                </span>
              </div>
              <v-spacer />
              <v-progress-linear
                indeterminate
                color="primary"
                height="3"
                rounded
                class="agent-banner__progress"
              />
              <v-btn
                v-if="bud.active_agent_task?.job_id"
                size="x-small"
                variant="tonal"
                color="warning"
                prepend-icon="mdi-close-circle-outline"
                :loading="cancellingAgent"
                @click="cancelRunningAgent"
              >
                Cancel
              </v-btn>
            </div>
          </div>

          <!-- Failed agent task — retry banner -->
          <v-alert
            v-if="bud.active_agent_task?.status === 'failed'"
            type="error"
            variant="tonal"
            density="compact"
            class="mx-12 mb-3"
          >
            <div class="d-flex align-center ga-2">
              <div class="flex-grow-1">
                <strong>Agent task failed</strong>
                <div v-if="bud.active_agent_task.error_message" class="text-caption">
                  {{ bud.active_agent_task.error_message }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  Attempt {{ bud.active_agent_task.attempt }}
                </div>
              </div>
              <v-btn
                color="primary"
                variant="tonal"
                size="small"
                @click="budStore.retryAgentTask(bud.id, bud.active_agent_task!.id)"
              >
                <v-icon start size="16">mdi-refresh</v-icon>
                Retry
              </v-btn>
            </div>
          </v-alert>

          <!-- Tabs + Toolbar row -->
          <div class="tabs-toolbar-row">
            <v-tabs v-model="activeTab" color="primary" density="compact">
              <v-tab value="requirements">Requirements</v-tab>
              <v-tab value="design">Design</v-tab>
              <v-tab value="tech-spec">Tech Spec</v-tab>
              <v-tab value="development">Development</v-tab>
              <v-tab value="code-review">Code Review</v-tab>
              <v-tab value="testing">Testing</v-tab>
              <v-tab v-if="uatStageEnabled" value="uat">UAT</v-tab>
              <v-tab value="prod">Prod</v-tab>
              <v-tab v-if="isClosed" value="closed">{{ bud.status === 'discarded' ? 'Discarded' : 'Closed' }}</v-tab>
            </v-tabs>
            <BUDSectionToolbar
              v-if="!isReadOnlyTab"
              :is-editing="isEditing"
              :agent-locked="agentLocked"
              :active-tab="activeTab"
              :current-section="currentSection"
              :editable="currentSectionEditable"
              :edit-lock-tooltip="editLockTooltip"
              @toggle-edit="toggleEdit"
              @export-section="downloadSection"
              @import-section="handleImportSection"
            />
          </div>

          <!-- Content panel -->
          <div class="section-content-panel">
            <v-tabs-window v-model="activeTab">
              <!-- Requirements -->
              <v-tabs-window-item value="requirements">
                <BUDRequirementsTab
                  v-if="bud"
                  :bud="bud"
                  :editing="editingContent"
                  :edit-value="editContent"
                  :agent-locked="agentLocked"
                  @update:edit-value="editContent = $event"
                  @save="saveContent"
                  @start-edit="toggleContentEdit"
                  @enrich="enrichWithAI"
                  @features-changed="loadTimeline"
                />
              </v-tabs-window-item>

              <!-- Design — eager so the panel's ``designAvailable``
                   watcher subscribes on initial render. The watcher
                   self-handles late-mount too (``immediate: true``),
                   but eager mounting avoids a one-tab-switch delay on
                   the auto-trigger when the user is on a non-Design
                   tab and flips status straight to Design. -->
              <v-tabs-window-item value="design" eager>
                <BUDDesignPanel
                  ref="designPanelRef"
                  :bud-id="bud.id"
                  :editable="bud.status === 'design'"
                  @chat-message="msg => chatMessages.push(msg)"
                  @switch-to-design="activeTab = 'design'"
                  @design-tab-change="loadChatHistory"
                />
              </v-tabs-window-item>

              <!-- Tech Spec -->
              <v-tabs-window-item value="tech-spec">
                <BUDTechSpecTab
                  v-if="bud"
                  :bud="bud"
                  :editing="editingTechSpec"
                  :edit-value="editTechSpec"
                  @update:edit-value="editTechSpec = $event"
                  @save="saveTechSpec"
                  @start-edit="toggleTechSpecEdit"
                />
              </v-tabs-window-item>

              <!-- Development -->
              <v-tabs-window-item value="development">
                <BUDTodoBoard :bud-id="bud.id" />
                <BUDPRChecklist
                  v-if="bud.impacted_repos?.length"
                  :bud-id="bud.id"
                />
                <BUDDevelopmentPanel
                  ref="devPanelRef"
                  :bud-id="bud.id"
                  :bud-number="bud.bud_number"
                  :has-tech-spec="!!bud.tech_spec_md"
                  :impacted-repos="bud.impacted_repos"
                  @download-tech-spec="downloadSection('tech_spec_md')"
                />
              </v-tabs-window-item>

              <!-- Code Review -->
              <v-tabs-window-item value="code-review">
                <!-- Not started: BUD hasn't reached code_review yet. The
                     "agent running" case is covered by the unified top banner
                     (search `agent-banner` in this file). -->
                <div v-if="!reachedCodeReview" class="text-center py-12">
                  <v-icon icon="mdi-code-tags-check" size="48" color="primary" class="mb-3 opacity-40" />
                  <div class="text-h6 font-weight-medium mb-2">Code review not started</div>
                  <div class="text-body-2 text-medium-emphasis">
                    Code review will begin when development is complete and moved to the code review stage.
                  </div>
                </div>

                <!-- Already past code review -->
                <div v-else-if="bud.status !== 'code_review'" class="text-center py-8">
                  <v-icon icon="mdi-check-circle-outline" size="48" color="success" class="mb-3 opacity-60" />
                  <div class="text-body-1 font-weight-medium">Code review completed</div>
                </div>

                <!-- Active: PR status board + Override CTA -->
                <BUDCodeReviewStatus
                  v-else
                  :bud-id="bud.id"
                  @transitioned="onCodeReviewTransitioned"
                />
              </v-tabs-window-item>

              <!-- Testing -->
              <v-tabs-window-item value="testing">
                <BUDQAPanel
                  :bud-id="bud.id"
                  :bud-number="bud.bud_number"
                  :test-plan-md="bud.test_plan_md"
                  :impacted-repos="bud.impacted_repos"
                  :active-agent-task="bud.active_agent_task"
                />
              </v-tabs-window-item>

              <!-- UAT (only when org has UAT stage enabled) -->
              <v-tabs-window-item v-if="uatStageEnabled" value="uat">
                <BUDReleaseStagePanel
                  :bud-id="bud.id"
                  stage="uat"
                  :has-stage-branch-configured="hasUatBranchConfigured"
                  :impacted-repos="bud.impacted_repos"
                />
              </v-tabs-window-item>

              <!-- Prod (always shown) -->
              <v-tabs-window-item value="prod">
                <BUDReleaseStagePanel
                  :bud-id="bud.id"
                  stage="prod"
                  :has-stage-branch-configured="hasMainBranchConfigured"
                  :impacted-repos="bud.impacted_repos"
                />
              </v-tabs-window-item>

              <!-- Closed / Discarded -->
              <v-tabs-window-item v-if="isClosed" value="closed">
                <BUDClosedTab v-if="bud" :bud="bud" :timeline-events="timelineEvents" />
              </v-tabs-window-item>

              <!-- Test Plan tab removed — test plan content is now part of QA tab -->
            </v-tabs-window>
          </div>

          <!-- Delivery Estimates (hidden when closed/discarded — no forecast needed) -->
          <BUDEstimationSection
            v-if="!isClosed"
            ref="estimationRef"
            :bud-id="bud.id"
            :current-phase="bud.status"
          />

          <!-- Linked Bugs -->
          <BUDBugsPanel :bud-id="bud.id" :bud-status="bud.status" class="mt-4" />

          <!-- Activity Timeline (collapsible) -->
          <BUDActivitySection :events="timelineEvents" :loading="timelineLoading" />

        </div>
      </template>

      <!-- Per-BUD AI skills picker -->
      <BUDSkillSettingsDialog
        v-if="bud"
        v-model="skillSettingsOpen"
        :bud-id="bud.id"
      />

      <!-- Delete confirmation -->
      <v-dialog v-model="confirmDelete" max-width="400">
        <v-card color="surface" class="pa-6">
          <div class="text-h6 mb-2">Delete BUD?</div>
          <div class="text-body-2 text-medium-emphasis mb-4">
            This will permanently delete BUD-{{ String(bud?.bud_number || 0).padStart(3, '0') }}: {{ bud?.title }}.
          </div>
          <v-card-actions class="pa-0">
            <v-spacer />
            <v-btn variant="text" @click="confirmDelete = false">Cancel</v-btn>
            <v-btn color="error" variant="flat" @click="handleDelete">Delete</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

    </div>

    <!-- Chat side panel -->
    <transition name="slide-panel">
      <ChatPanel
        v-if="chatOpen && bud"
        :section-label="currentSectionLabel"
        :messages="chatMessages"
        :loading="chatLoading"
        :status-message="chatStatusMessage"
        :stage-gate-message="stageGateMessage"
        :chat-in-progress-banner="chatInProgressBanner"
        :retry-prompt="retryPrompt"
        :designs="chatDesignOptions"
        :selected-design-id="activeDesignTabId"
        @close="chatOpen = false"
        @send="handleChatSend"
        @cancel="handleChatCancel"
        @new-session="startNewSession"
        @retry="manualRetry"
        @select-design="handleChatSelectDesign"
      />
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { useAuthStore } from '@/stores/auth'
import { useMembersStore } from '@/stores/members'
import { useBudChat } from '@/composables/useBudChat'
import { useBudStatusTransitions } from '@/composables/useBudStatusTransitions'
import '@/components/buds/agent-banner.css'
import { subscribe, unsubscribe } from '@/services/socket'
import { onSocketReconnect } from '@/services/wsReconnect'
import { useMarkdownSection } from '@/composables/useMarkdownSection'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import {
  BUD_STATUS_ORDER,
  BUD_STATUS_LABELS,
  BUD_STATUS_COLORS,
  BUD_SECTIONS,
  VALID_BUD_TABS,
  TAB_TO_SECTION,
  isSectionEditable,
  isSectionChatable,
} from '@/types'
import type { BUDSectionKey, TimelineEvent } from '@/types'
import ChatPanel from '@/components/buds/ChatPanel.vue'
import BUDEstimationSection from '@/components/buds/BUDEstimationSection.vue'
import BUDActivitySection from '@/components/buds/BUDActivitySection.vue'
import BUDHeader from '@/components/buds/BUDHeader.vue'
import BUDSkillSettingsDialog from '@/components/buds/BUDSkillSettingsDialog.vue'
import BUDDesignPanel from '@/components/buds/BUDDesignPanel.vue'
import BUDDevelopmentPanel from '@/components/buds/BUDDevelopmentPanel.vue'
import BUDTodoBoard from '@/components/buds/BUDTodoBoard.vue'
import BUDPRChecklist from '@/components/buds/BUDPRChecklist.vue'
import BUDCodeReviewStatus from '@/components/buds/BUDCodeReviewStatus.vue'
import BUDQAPanel from '@/components/buds/BUDQAPanel.vue'
import BUDBugsPanel from '@/components/buds/BUDBugsPanel.vue'
import BUDReleaseStagePanel from '@/components/buds/BUDReleaseStagePanel.vue'
import BUDWorkflowActions from '@/components/buds/BUDWorkflowActions.vue'
import BUDRequirementsTab from '@/components/buds/BUDRequirementsTab.vue'
import BUDTechSpecTab from '@/components/buds/BUDTechSpecTab.vue'
import BUDClosedTab from '@/components/buds/BUDClosedTab.vue'
import BUDSectionToolbar from '@/components/buds/BUDSectionToolbar.vue'
import BUDStatusDialogs from '@/components/buds/BUDStatusDialogs.vue'
import { useBudLinkedFeaturesStore } from '@/stores/budLinkedFeatures'
import { useSettingsStore } from '@/stores/settings'

const route = useRoute()
const router = useRouter()
const budStore = useBUDStore()
const authStore = useAuthStore()
const membersStore = useMembersStore()
const settingsStore = useSettingsStore()
const budLinkedFeaturesStore = useBudLinkedFeaturesStore()

const bud = computed(() => budStore.currentBUD)

// True iff every phase in auto_generate_phases is off (or the map is
// empty / null entirely). Drives the External-LLM banner — we only
// surface the "connect your local AI" hint when there's literally no
// auto-fired phase for the user to wait on.
const isExternalLlmMode = computed(() => {
  const phases = bud.value?.auto_generate_phases
  if (!phases) return true
  return !Object.values(phases).some(Boolean)
})

const activeTab = ref('requirements')
const confirmDelete = ref(false)
const skillSettingsOpen = ref(false)

// Org-level UAT toggle. Hidden when false: the UAT tab disappears, and
// any active session that's currently on the UAT tab falls back to Prod.
// Default to true so the tab is visible during the brief settings load.
const uatStageEnabled = computed(
  () => settingsStore.connections.budStages?.uatEnabled ?? true,
)

// Closed / discarded state \u2014 drives the conditional Closed tab.
const isClosed = computed(
  () => bud.value?.status === 'closed' || bud.value?.status === 'discarded',
)

// "Read-only" tabs hide the section toolbar (Edit/Export/Import).
const READ_ONLY_TABS = new Set([
  'development',
  'code-review',
  'testing',
  'uat',
  'prod',
  'closed',
])
const isReadOnlyTab = computed(() => READ_ONLY_TABS.has(activeTab.value))

// Empty-state CTA on the release-stage panels: was a relevant branch
// configured on ANY of this BUD's impacted repos? When false, the panel
// shows a "Configure UAT branch" or "Configure production branch" link.
// Branch info isn't on bud.impacted_repos directly \u2014 we look it up via
// the settings store's repo list which the layout already loads.
const hasUatBranchConfigured = computed(() => {
  const ids = new Set(
    (bud.value?.impacted_repos ?? []).map((r: { repo_id?: string }) => r.repo_id),
  )
  return settingsStore.repos.some(
    (r) => ids.has(r.id) && !!r.uatBranch,
  )
})
const hasMainBranchConfigured = computed(() => {
  const ids = new Set(
    (bud.value?.impacted_repos ?? []).map((r: { repo_id?: string }) => r.repo_id),
  )
  return settingsStore.repos.some(
    (r) => ids.has(r.id) && !!r.mainBranch,
  )
})

// If UAT is currently selected and the toggle gets flipped off (e.g.
// admin disables UAT in another tab), drop back to Prod so the tab strip
// stays consistent with the visible content.
watch(uatStageEnabled, (enabled) => {
  if (!enabled && activeTab.value === 'uat') {
    activeTab.value = 'prod'
  }
})

// Child component refs
const designPanelRef = ref<InstanceType<typeof BUDDesignPanel> | null>(null)
const devPanelRef = ref<InstanceType<typeof BUDDevelopmentPanel> | null>(null)
const workflowRef = ref<InstanceType<typeof BUDWorkflowActions> | null>(null)

// Status-transition orchestration: guards (code_review PR check,
// testing → uat/prod pending-cases check, manual-merge override),
// in-flight banner, backend-error snackbar, cancel-running-agent.
// All dialog/banner/snackbar state lives in the composable; the
// view hands the whole controller to <BUDStatusDialogs> for the UI
// and pulls out only the bits the header / agent-banner need.
const statusController = useBudStatusTransitions({
  getBud: () => bud.value,
  setActiveTab: (tab) => { activeTab.value = tab },
  getStatusTabMap: () => STATUS_TAB_MAP,
  // Kept only so manual call sites (none today) still work; the
  // auto-trigger on status → design is panel-side via a watcher on
  // budStore.designAvailable. No more parent→child ref-call race.
  triggerDesignGeneration: () => designPanelRef.value?.triggerDesignGeneration(),
  reloadTimeline: () => loadTimeline(),
})
const {
  updateStatus,
  cancelRunningAgent,
  cancellingAgent,
  cancelDesign,
  cancellingDesignId,
} = statusController

// Designs currently being generated. Rendered as one banner per row
// during the design phase so each repo's wireframe gets its own
// progress indicator + cancel button (each design owns a separate
// Claude job id).
const generatingDesigns = computed(
  () => bud.value?.designs?.filter((d) => d.status === 'generating') ?? [],
)

// Repo picker for the chat panel — only surfaced when the user is
// on the design section. The chat-panel itself renders the dropdown
// only when there are 2+ entries, so we hand it the full list and
// let it decide. The "active" id mirrors the design sub-tab inside
// BUDDesignPanel so the dropdown selection and the visible tab stay
// in sync.
const chatDesignOptions = computed(() => {
  if (currentSection.value !== 'design') return []
  return (bud.value?.designs ?? []).map((d) => ({
    id: d.id,
    repoName: d.repo_name,
  }))
})
const activeDesignTabId = computed(() => designPanelRef.value?.activeDesignTab ?? undefined)

function handleChatSelectDesign(designId: string): void {
  // Drive the design sub-tab through its exposed setter; the existing
  // watch(activeDesignTab) → emit('design-tab-change') → loadChatHistory
  // wiring then reloads the chat for the newly-selected design.
  designPanelRef.value?.setActiveDesignTab(designId)
}

const canApprove = computed(() => {
  const role = authStore.user?.role
  return role === 'tech_lead' || role === 'manager' || role === 'org_owner'
})

// "Has the BUD reached the code_review phase yet?" — matches the
// BUD_STATUS_ORDER.indexOf pattern used by BUDEstimateTimeline.vue and
// BUDBoard.vue for phase-reached checks.
const _codeReviewPhaseIdx = BUD_STATUS_ORDER.indexOf('code_review')
const reachedCodeReview = computed(() => {
  const s = bud.value?.status
  if (!s) return false
  return BUD_STATUS_ORDER.indexOf(s) >= _codeReviewPhaseIdx
})

// Code Review → Testing transition handler. BUDCodeReviewStatus emits
// this after a successful override. The tab auto-switches to Testing
// via the STATUS_TAB_MAP watcher once fetchBUD picks up the new status,
// so no manual activeTab assignment needed.
async function onCodeReviewTransitioned(): Promise<void> {
  if (!bud.value) return
  await Promise.all([budStore.fetchBUD(bud.value.id), loadTimeline()])
}

const isCurrentAssignee = computed(() =>
  bud.value?.assignee_id != null && authStore.user?.id === bud.value.assignee_id,
)

// Timeline state (rendered by BUDActivitySection; events are also
// consumed by the Closed-tab computeds below, so the ref stays in the
// view).
const timelineEvents = ref<TimelineEvent[]>([])
const timelineLoading = ref(false)

// Delivery-estimates ref — used to trigger reloads after status
// changes, agent runs, and webhook activity (the section auto-loads on
// mount/budId change; this is for the cross-cutting refresh paths).
const estimationRef = ref<InstanceType<typeof BUDEstimationSection> | null>(null)
function reloadEstimates(): void {
  estimationRef.value?.loadEstimates()
}

// Markdown section editing via composable
const { editing: editingContent, editValue: editContent, toggle: toggleContentEdit, save: saveContent } =
  useMarkdownSection('requirements_md', bud)
const { editing: editingTechSpec, editValue: editTechSpec, toggle: toggleTechSpecEdit, save: saveTechSpec } =
  useMarkdownSection('tech_spec_md', bud)
const { editing: editingTestPlan, toggle: toggleTestPlanEdit } =
  useMarkdownSection('test_plan_md', bud)

// Chat orchestration (state + history + send + Jira-enrich seed).
// The composable depends on `currentSection`, `designPanelRef`, and
// the per-section editor refs, all of which are declared below — but
// composables only read these on invocation, so forward references
// resolve fine at call time.
const {
  chatOpen, chatLoading, chatMessages, chatStatusMessage, currentSessionId,
  stageGateMessage, chatInProgressBanner, retryPrompt,
  loadChatHistory, startNewSession, handleChatSend, handleChatCancel, manualRetry, enrichWithAI,
} = useBudChat({
  getBud: () => bud.value,
  getCurrentSection: () => currentSection.value,
  getDesignTabId: () => designPanelRef.value?.activeDesignTab,
  setActiveTab: (tab) => { activeTab.value = tab },
  syncEditor: (section, content) => {
    if (section === 'requirements_md' && editingContent.value) {
      editContent.value = content
    } else if (section === 'tech_spec_md' && editingTechSpec.value) {
      editTechSpec.value = content
    }
  },
  onDesignContentUpdated: async () => {
    if (bud.value) await designPanelRef.value?.loadDesigns()
    designPanelRef.value?.refreshDesignPreview()
  },
})

// Status dropdown items. Uses the org-filtered phase order so UAT is
// hidden when the org has it disabled (see usePhaseOrder). This is the
// ONE place BUDDetail renders a user-facing phase list — everything else
// here uses BUD_STATUS_ORDER for monotonic phase-reached checks, which
// must stay on the canonical unfiltered list.
const { phaseOrder } = usePhaseOrder()
const statusItems = computed(() =>
  phaseOrder.value.map(s => ({
    title: BUD_STATUS_LABELS[s],
    value: s,
  })),
)

const statusColor = computed(() =>
  bud.value ? BUD_STATUS_COLORS[bud.value.status] || 'default' : 'default',
)

const currentSection = computed<BUDSectionKey>(() =>
  TAB_TO_SECTION[activeTab.value] ?? 'requirements_md',
)

const currentSectionLabel = computed(() =>
  BUD_SECTIONS[currentSection.value].label,
)

// Edit is allowed only when the BUD's current status owns the active
// section. e.g. requirements is locked the moment we move out of `bud`.
// Backend enforces the same rule (HTTP 409) — see
// backend/app/services/bud_edit_policy.py.
const currentSectionEditable = computed(() =>
  isSectionEditable(currentSection.value, bud.value?.status),
)

// Chat lock — mirrors the edit lock above, using the chat-specific
// section/stage map (SECTION_CHAT_STAGES). Backend enforces the same
// rule via HTTP 409; this predicate keeps the AI button consistent
// with that contract so the user can't even open chat when the gate
// would reject the first send.
const currentSectionChatable = computed(() =>
  isSectionChatable(currentSection.value, bud.value?.status),
)

// Section → human label for the "Move the BUD to <X> to edit" tooltip.
// ``development`` is here only to keep TypeScript happy — it's in
// READ_ONLY_TABS, so the toolbar (and this tooltip) never renders on
// that tab.
const EDIT_LOCK_PHASE_LABEL: Record<BUDSectionKey, string | null> = {
  requirements_md: 'BUD',
  design: 'Design',
  tech_spec_md: 'Tech Architecture',
  testing: 'Testing',
  code_review: 'Code Review',
  development: null,
}
const editLockTooltip = computed(() => {
  const required = EDIT_LOCK_PHASE_LABEL[currentSection.value]
  if (!required) return 'This section is read-only'
  return `Move the BUD to ${required} to edit this section`
})

const isEditing = computed(() => {
  if (activeTab.value === 'tech-spec') return editingTechSpec.value
  if (activeTab.value === 'test-plan') return editingTestPlan.value
  if (activeTab.value === 'design') return designPanelRef.value?.editingDesignId !== null
  return editingContent.value
})

const agentLocked = computed(() => {
  const t = bud.value?.active_agent_task
  const taskActive = !!t && (t.status === 'pending' || t.status === 'running')
  // Phase chain (assignment → todo → estimation) emits agent_activity
  // events the workflow component aggregates into a counter. While any
  // stage is in flight, treat the BUD as locked so the status menu and
  // every other gated control are disabled, just like task-active.
  const phaseActive = !!workflowRef.value?.phaseInFlight
  return taskActive || phaseActive
})

// Top-level cleanup target for the BUD-activity subscription. Populated
// from inside onMounted once the route id is known; fired by the
// synchronous onUnmounted below. We can't call `onUnmounted` from
// inside the async onMounted callback — Vue 3 warns "no active
// component instance" because setup() has long since returned by then.
let budActivityCleanup: (() => void) | null = null

onUnmounted(() => {
  budActivityCleanup?.()
  budActivityCleanup = null
})

onMounted(async () => {
  const tabParam = route.query.tab as string | undefined
  if (tabParam && VALID_BUD_TABS.has(tabParam)) {
    activeTab.value = tabParam
  }

  const id = route.params.id as string
  await budStore.fetchBUD(id)

  // Auto-select tab based on BUD status (unless explicit ?tab= param)
  if (!tabParam && bud.value) {
    const defaultTab = STATUS_TAB_MAP[bud.value.status]
    if (defaultTab) activeTab.value = defaultTab
  }

  await loadChatHistory()
  membersStore.fetchMembers()
  loadTimeline()
  // BUDEstimationSection auto-loads on mount via its budId watcher; no
  // explicit call needed here.
  // Settings store powers the UAT toggle visibility (uatStageEnabled)
  // and the release-stage panels' "configure branch" CTA
  // (hasUatBranchConfigured / hasMainBranchConfigured). Both actions
  // are no-ops if the data is already cached, so this is cheap.
  if (!settingsStore.connections.budStages) settingsStore.fetchConnections()
  if (settingsStore.repos.length === 0) settingsStore.fetchRepos()

  // Subscribe to BUD activity events (PR opened/merged/comment via webhook)
  const budActivityTopic = `bud:${id}:activity`
  const handleBudActivity = () => {
    budStore.fetchBUD(id)
    loadTimeline()
    reloadEstimates()
  }
  subscribe(budActivityTopic, handleBudActivity)
  // Also resync on WS reconnect — webhook-driven activity events that
  // landed while we were disconnected (backend restart, browser sleep)
  // are not buffered. Refetching state on reconnect mirrors what a
  // page-refresh does and keeps the timeline / PR-status banners
  // accurate without the user knowing they were briefly offline.
  const unregisterReconnect = onSocketReconnect(handleBudActivity)
  // Stash cleanup so the top-level onUnmounted (registered synchronously
  // in setup) can fire it. Calling onUnmounted from inside an async
  // onMounted callback warns "no active component instance" in Vue 3.
  budActivityCleanup = () => {
    unsubscribe(budActivityTopic, handleBudActivity)
    unregisterReconnect()
  }
})

// Single source of truth for status → tab mapping
const STATUS_TAB_MAP: Record<string, string> = {
  bud: 'requirements',
  design: 'design',
  tech_arch: 'tech-spec',
  development: 'development',
  code_review: 'code-review',
  testing: 'testing',
  uat: 'uat',
  prod: 'prod',
  closed: 'closed',
  discarded: 'closed',
}
watch(
  () => bud.value?.status,
  (newStatus) => {
    if (newStatus && STATUS_TAB_MAP[newStatus]) {
      activeTab.value = STATUS_TAB_MAP[newStatus]
    }
  },
)

// Track active agent task. We watch the primitive `job_id` (not the full
// task object) so the watcher fires only when the *identity* of the
// running task changes — every `fetchBUD` produces a fresh
// `active_agent_task` object reference, and watching the object would
// re-run `trackAgentTask` → `startTracking` → one `/v1/jobs/{id}/status`
// REST call per refetch. That was the source of the status-API loop
// observed when reconnect handlers refetched the BUD.
const activeAgentJobId = computed(() => {
  const t = bud.value?.active_agent_task
  if (!t?.job_id) return null
  if (t.status !== 'pending' && t.status !== 'running') return null
  // During the design phase the per-design banners own job tracking
  // — each design row carries its own job_id and the task row only
  // records one of them ("first wins"). Tracking task.job_id here
  // produces an infinite loop after a per-design cancel: the
  // tracker receives the cancelled state, onError calls fetchBUD,
  // fetchBUD toggles ``loading`` which unmounts/remounts the
  // workflow ref, the watch re-fires with the same job id but a new
  // ref instance, the tracker restarts on the still-cancelled job,
  // and so on. Skipping the task-level tracker during design phase
  // lets the per-design trackers in BUDDesignPanel — keyed on each
  // design's real job_id — be the single source of truth.
  if (bud.value?.status === 'design') return null
  return t.job_id
})
watch(
  [activeAgentJobId, workflowRef],
  ([jobId, wf]) => {
    if (!jobId || !wf) return
    const task = bud.value?.active_agent_task
    if (task) wf.trackAgentTask(task)
  },
  { immediate: true },
)

// Subscribe to the org-scoped agent_activity channel as soon as the BUD
// is loaded (or the workflow component mounts). This is the universal
// "any AI worker for this BUD is running" stream — covers phases that
// don't create a BUDAgentTask row (assignment, todo, estimation) and
// keeps the banner + agentLocked accurate end-to-end. The workflow
// component dedupes on bud-id so re-firing the watch is safe.
watch(
  [() => bud.value?.id, () => authStore.user?.org_id, workflowRef],
  ([budId, orgId, wf]) => {
    if (!budId || !orgId || !wf) return
    wf.trackAgentActivity(orgId, budId)
  },
  { immediate: true },
)

onUnmounted(() => {
  workflowRef.value?.stopAgentActivity()
})

// Close the chat panel when the active section becomes non-chattable
// (tab switch into a locked section, or a stage transition that locks
// the currently-open section). Mirrors the AI button's disabled state
// so the panel doesn't linger in a state where every send would 409.
watch(currentSectionChatable, (chatable) => {
  if (!chatable && chatOpen.value) chatOpen.value = false
})

// Auto-close chat panel when an OUTSIDE agent starts; reload timeline when
// any agent finishes. Skip the close when the chat itself just kicked off the
// run (``chatLoading`` is true) — otherwise the user loses the panel they're
// actively chatting in the moment they send a message.
watch(agentLocked, (locked, wasLocked) => {
  if (locked && !chatLoading.value && chatOpen.value) chatOpen.value = false
  if (!locked && wasLocked) {
    loadTimeline()
    reloadEstimates()
    // The PM agent writes bud_feature_link rows from its JSON-fence tail
    // on every run, regardless of which surface kicked it off (chat panel,
    // stage transition, or BUD creation). agentLocked flipping back to
    // false is the universal "agent finished" signal — refetch links here
    // so panels stay in sync without having to wire each surface separately.
    if (bud.value) void budLinkedFeaturesStore.fetch(bud.value.id)
  }
})

// Load chat history when switching tabs
watch(activeTab, () => {
  currentSessionId.value = undefined
  loadChatHistory()
})

async function handleSaveTitle(title: string): Promise<void> {
  if (!bud.value) return
  await budStore.updateBUD(bud.value.id, { title })
  await loadTimeline()
}

// Unified toggle for whichever tab is active. Guarded by
// currentSectionEditable so keyboard shortcuts and programmatic toggles
// honor the same phase rule as the toolbar's Edit button.
function toggleEdit(): void {
  if (!currentSectionEditable.value) return
  if (activeTab.value === 'tech-spec') toggleTechSpecEdit()
  else if (activeTab.value === 'test-plan') toggleTestPlanEdit()
  else if (activeTab.value === 'design') designPanelRef.value?.toggleDesignEdit()
  else toggleContentEdit()
}

async function handleDelete(): Promise<void> {
  if (!bud.value) return
  const ok = await budStore.deleteBUD(bud.value.id)
  if (ok) router.push('/buds')
}

// ── Export / Import ───────────────────────────────────

function downloadSection(section: string): void {
  if (!bud.value) return
  const budRef = `BUD-${String(bud.value.bud_number).padStart(3, '0')}`

  // Design tab exports the active design's HTML
  if (section === 'design') {
    const html = designPanelRef.value?.activeDesignObj?.design_html
    if (!html) return
    const repoName = designPanelRef.value?.activeDesignObj?.repo_name || 'default'
    const blob = new Blob([html], { type: 'text/html' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${budRef}-design-${repoName}.html`
    a.click()
    URL.revokeObjectURL(a.href)
    return
  }

  const content = (bud.value as Record<string, unknown>)[section] as string || ''
  const suffix = section.replace('_md', '').replace('_', '-')

  const blob = new Blob([content], { type: 'text/markdown' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${budRef}-${suffix}.md`
  a.click()
  URL.revokeObjectURL(a.href)
}

async function handleImportSection(section: string, file: File): Promise<void> {
  if (!bud.value) return
  await budStore.importBUD(bud.value.id, section, file)
}

async function loadTimeline(): Promise<void> {
  if (!bud.value) return
  timelineLoading.value = true
  timelineEvents.value = await budStore.fetchTimeline(bud.value.id)
  timelineLoading.value = false
}

async function handleAssigneeChange(memberId: string | null): Promise<void> {
  if (!bud.value) return
  await budStore.updateBUD(bud.value.id, { assignee_id: memberId } as never)
  await loadTimeline()
}

</script>

<style scoped>
/* ── Layout ──────────────────────────────────── */
.bud-detail-layout {
  display: flex;
  height: 100%;
  overflow: hidden;
}

.bud-main {
  flex: 1;
  overflow-y: auto;
}

.bud-page-content {
  padding: 24px 32px 48px;
}

/* ── Tabs + Toolbar row ────────────────────────── */
.tabs-toolbar-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  margin-bottom: 0;
}

/* ── Content panel ─────────────────────────────── */
.section-content-panel {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-top: none;
  border-radius: 0 0 8px 8px;
  background: rgb(var(--v-theme-surface));
  min-height: 300px;
}

/* ── Panel slide transition ────────────────────── */
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: all 0.25s ease;
}

.slide-panel-enter-from,
.slide-panel-leave-to {
  width: 0;
  min-width: 0;
  opacity: 0;
}
</style>
