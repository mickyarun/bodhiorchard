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
            @back="router.push('/buds')"
            @update:chat-open="chatOpen = $event"
            @change-assignee="handleAssigneeChange"
            @update-status="updateStatus"
            @delete="confirmDelete = true"
            @save-title="handleSaveTitle"
          />

          <!-- Workflow banners, approval/reject/reassign dialogs, repo confirmation -->
          <BUDWorkflowActions
            ref="workflowRef"
            :bud="bud"
            :can-approve="canApprove"
            :is-current-assignee="isCurrentAssignee"
            @reload-timeline="loadTimeline(); reloadEstimates()"
          />

          <!-- Status change progress -->
          <div
            v-if="statusChanging"
            class="agent-banner mx-12 mb-3"
          >
            <div class="d-flex align-center ga-3">
              <v-icon icon="mdi-swap-horizontal" size="20" color="primary" />
              <div class="d-flex flex-column agent-banner__text">
                <span class="text-body-2 font-weight-medium">Updating status...</span>
                <span class="text-caption text-medium-emphasis">Assigning {{ PHASE_ROLE_LABELS[statusChangeTarget] || 'team member' }}</span>
              </div>
              <v-spacer />
              <v-progress-linear
                indeterminate
                color="primary"
                height="3"
                rounded
                class="agent-banner__progress"
              />
            </div>
          </div>

          <!-- Agent generating banner (unified for PRD, tech arch, code review) -->
          <div
            v-if="workflowRef?.agentGenerating"
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
            <div v-if="!isReadOnlyTab" class="toolbar-actions">
              <v-btn
                variant="text"
                size="small"
                class="toolbar-btn"
                :disabled="agentLocked"
                @click="toggleEdit"
              >
                <v-icon size="15" class="mr-1">{{ isEditing ? 'mdi-eye-outline' : 'mdi-pencil-outline' }}</v-icon>
                {{ isEditing ? 'Preview' : 'Edit' }}
              </v-btn>
              <span class="toolbar-sep" />
              <v-btn
                variant="text"
                size="small"
                class="toolbar-btn"
                :disabled="agentLocked"
                @click="downloadSection(currentSection)"
              >
                <v-icon size="15" class="mr-1">mdi-tray-arrow-down</v-icon>
                Export
              </v-btn>
              <v-btn
                v-if="activeTab !== 'design'"
                variant="text"
                size="small"
                class="toolbar-btn"
                :disabled="agentLocked"
                @click="triggerUpload(currentSection)"
              >
                <v-icon size="15" class="mr-1">mdi-tray-arrow-up</v-icon>
                Import
              </v-btn>
            </div>
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

              <!-- Design -->
              <v-tabs-window-item value="design">
                <BUDDesignPanel
                  ref="designPanelRef"
                  :bud-id="bud.id"
                  @chat-message="msg => chatMessages.push(msg)"
                  @switch-to-design="activeTab = 'design'"
                  @design-tab-change="loadChatHistory"
                />
              </v-tabs-window-item>

              <!-- Tech Spec -->
              <v-tabs-window-item value="tech-spec">
                <textarea
                  v-if="editingTechSpec"
                  v-model="editTechSpec"
                  class="section-editor"
                  placeholder="Technical implementation details..."
                  @blur="saveTechSpec"
                />
                <div
                  v-else-if="bud.tech_spec_md"
                  class="rendered-markdown"
                  v-html="renderMarkdown(bud.tech_spec_md)"
                />
                <div v-else class="section-empty">
                  <v-icon icon="mdi-code-braces" size="40" class="mb-3" />
                  <div>No tech spec yet</div>
                  <v-btn variant="tonal" size="small" class="mt-3" @click="toggleTechSpecEdit">
                    <v-icon start size="15">mdi-pencil-outline</v-icon>
                    Start writing
                  </v-btn>
                </div>
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
                <div class="pa-4">
                  <v-alert
                    :type="bud.status === 'discarded' ? 'error' : 'info'"
                    variant="tonal"
                    density="compact"
                    class="mb-5"
                  >
                    <div class="d-flex align-center ga-2">
                      <v-icon :icon="bud.status === 'discarded' ? 'mdi-delete-outline' : 'mdi-check-circle-outline'" />
                      <div class="flex-grow-1">
                        <div class="font-weight-medium">
                          {{ bud.status === 'discarded' ? 'This BUD was discarded' : 'This BUD is closed' }}
                        </div>
                        <div v-if="closedEvent" class="text-caption text-medium-emphasis">
                          {{ closedEvent.actor_name || 'System' }} &middot; {{ formatClosedDate(closedEvent.created_at) }}
                        </div>
                      </div>
                    </div>
                  </v-alert>

                  <!-- Release / closure date -->
                  <div v-if="closedEvent" class="mb-5">
                    <div class="text-overline text-medium-emphasis mb-2">
                      {{ bud.status === 'discarded' ? 'Discarded on' : 'Completed on' }}
                    </div>
                    <div class="d-flex align-center ga-2">
                      <v-icon icon="mdi-calendar-check" size="18" color="success" />
                      <span class="text-body-1 font-weight-medium">
                        {{ formatClosedDate(closedEvent.created_at) }}
                      </span>
                    </div>
                  </div>

                  <!-- Closure reason (from status_override or status_change detail) -->
                  <div v-if="closedReason" class="mb-5">
                    <div class="text-overline text-medium-emphasis mb-2">Reason</div>
                    <v-card variant="outlined" class="pa-3">
                      <div class="text-body-2">{{ closedReason }}</div>
                    </v-card>
                  </div>

                  <!-- Previous status before closure -->
                  <div v-if="closedFrom" class="mb-5">
                    <div class="text-overline text-medium-emphasis mb-2">Closed from</div>
                    <v-chip variant="tonal" :color="BUD_STATUS_COLORS[closedFrom as BUDStatus] || 'grey'" size="small">
                      {{ BUD_STATUS_LABELS[closedFrom as BUDStatus] || closedFrom }}
                    </v-chip>
                  </div>

                  <!-- Closure timeline events -->
                  <div v-if="closedTimelineEvents.length" class="mb-5">
                    <div class="text-overline text-medium-emphasis mb-2">Timeline</div>
                    <div class="d-flex flex-column ga-2">
                      <div
                        v-for="event in closedTimelineEvents"
                        :key="event.id"
                        class="d-flex align-center ga-2 pa-2 rounded"
                        style="border: 1px solid rgba(255,255,255,0.08)"
                      >
                        <v-icon
                          :icon="event.event_type === 'status_change' ? 'mdi-swap-horizontal' : 'mdi-information-outline'"
                          size="18"
                          color="primary"
                        />
                        <div class="flex-grow-1">
                          <span class="text-body-2">
                            {{ event.event_type === 'status_change'
                              ? `Status changed: ${event.detail?.from || '?'} → ${event.detail?.to || '?'}`
                              : event.event_type.replace(/_/g, ' ')
                            }}
                          </span>
                          <div class="text-caption text-medium-emphasis">
                            {{ event.actor_name || 'System' }} &middot; {{ formatClosedDate(event.created_at) }}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
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

          <!-- Status Override Reason Dialog -->
          <v-dialog v-model="overrideReasonDialog" max-width="420">
            <v-card color="surface" class="pa-5">
              <div class="text-subtitle-1 font-weight-medium mb-3">
                Advance to Testing
              </div>
              <div class="text-body-2 text-medium-emphasis mb-3">
                Some PRs aren't merged yet. Please explain why you're manually
                advancing to QA.
              </div>
              <v-textarea
                v-model="overrideReasonText"
                label="Reason (required)"
                rows="3"
                :rules="[v => !!v?.trim() || 'Reason is required']"
              />
              <v-card-actions class="pa-0 mt-2">
                <v-spacer />
                <v-btn variant="text" @click="overrideReasonDialog = false">Cancel</v-btn>
                <v-btn
                  color="warning"
                  variant="flat"
                  :disabled="!overrideReasonText.trim()"
                  @click="confirmOverrideStatus"
                >
                  Advance
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-dialog>

          <!-- No Open PR Warning Dialog -->
          <v-dialog v-model="showNoPRWarningDialog" max-width="420">
            <v-card color="surface" class="pa-5">
              <div class="text-subtitle-1 font-weight-medium mb-3">
                No PR is open to review
              </div>
              <div class="text-body-2 text-medium-emphasis mb-4">
                All PRs are merged or no PR has been raised yet. Code review
                will start only after a PR is raised on GitHub.
              </div>
              <v-card-actions class="pa-0">
                <v-spacer />
                <v-btn variant="text" @click="showNoPRWarningDialog = false">Cancel</v-btn>
                <v-btn color="primary" variant="flat" @click="confirmNoPRWarning">
                  Proceed
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-dialog>

          <!-- Pending manual test cases dialog.
               Triggered when the tester tries to advance testing → uat
               (or testing → prod on a UAT-disabled org) while any manual
               case is still in pending state. Hard gate — no Proceed
               button, the user must go resolve the cases first. -->
          <v-dialog v-model="showPendingCasesDialog" max-width="500">
            <v-card color="surface" class="pa-5">
              <div class="d-flex align-center ga-2 mb-3">
                <v-icon icon="mdi-clipboard-alert-outline" color="warning" />
                <div class="text-subtitle-1 font-weight-medium">
                  Manual test cases still pending
                </div>
              </div>
              <div class="text-body-2 text-medium-emphasis mb-3">
                Cannot advance to
                <strong>{{ pendingCasesTarget }}</strong> —
                {{ pendingCasesList.length }} manual test case{{ pendingCasesList.length === 1 ? '' : 's' }}
                {{ pendingCasesList.length === 1 ? 'is' : 'are' }} still awaiting a result.
              </div>
              <div class="pending-cases-list mb-4">
                <div
                  v-for="tc in pendingCasesList.slice(0, 8)"
                  :key="tc.id"
                  class="pending-case-row"
                >
                  <v-icon icon="mdi-circle-outline" size="14" class="mr-2 opacity-60" />
                  <strong class="mr-1">{{ tc.id }}</strong>
                  <span class="text-truncate">{{ tc.title }}</span>
                </div>
                <div
                  v-if="pendingCasesList.length > 8"
                  class="text-caption text-medium-emphasis mt-1 pl-6"
                >
                  and {{ pendingCasesList.length - 8 }} more…
                </div>
              </div>
              <div class="text-caption text-medium-emphasis mb-4">
                Open the QA tab, mark each case as pass, fail, blocked, or
                skipped, then try again.
              </div>
              <v-card-actions class="pa-0">
                <v-spacer />
                <v-btn variant="text" @click="showPendingCasesDialog = false">
                  Close
                </v-btn>
                <v-btn
                  color="primary"
                  variant="flat"
                  prepend-icon="mdi-clipboard-check-outline"
                  @click="openQATab"
                >
                  Open QA tab
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-dialog>

          <!-- Snackbar surfaces backend rejections (permission denied,
               race conditions where the frontend preempt didn't catch
               a pending case, etc.) so the user sees WHY the PATCH was
               rejected instead of a blank failure. -->
          <v-snackbar
            v-model="statusErrorSnackbar"
            color="error"
            location="bottom"
            :timeout="6000"
            multi-line
          >
            {{ statusErrorMessage }}
            <template #actions>
              <v-btn
                variant="text"
                @click="statusErrorSnackbar = false"
              >
                Dismiss
              </v-btn>
            </template>
          </v-snackbar>

          <!-- Activity Timeline (collapsible) -->
          <BUDActivitySection :events="timelineEvents" :loading="timelineLoading" />

        </div>
      </template>

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

      <!-- Hidden file input -->
      <input
        ref="fileInput"
        type="file"
        accept=".md,.txt,.markdown,.html,.htm"
        style="display: none;"
        @change="handleFileUpload"
      />
    </div>

    <!-- Chat side panel -->
    <transition name="slide-panel">
      <ChatPanel
        v-if="chatOpen && bud"
        :section-label="currentSectionLabel"
        :messages="chatMessages"
        :loading="chatLoading"
        :status-message="chatStatusMessage"
        @close="chatOpen = false"
        @send="handleChatSend"
        @new-session="startNewSession"
      />
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { useAuthStore } from '@/stores/auth'
import { useMembersStore } from '@/stores/members'
import { useJobSocket } from '@/composables/useJobSocket'
import { friendlyAgentError } from '@/types/agentErrors'
import { subscribe, unsubscribe } from '@/services/socket'
import { onSocketReconnect } from '@/services/wsReconnect'
import { useMarkdownSection } from '@/composables/useMarkdownSection'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import { BUD_STATUS_ORDER, BUD_STATUS_LABELS, BUD_STATUS_COLORS, BUD_SECTIONS, VALID_BUD_TABS, TAB_TO_SECTION } from '@/types'
import type { BUDSectionKey, BUDStatus, TimelineEvent } from '@/types'
import ChatPanel from '@/components/buds/ChatPanel.vue'
import BUDEstimationSection from '@/components/buds/BUDEstimationSection.vue'
import BUDActivitySection from '@/components/buds/BUDActivitySection.vue'
import BUDHeader from '@/components/buds/BUDHeader.vue'
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
import { useBudLinkedFeaturesStore } from '@/stores/budLinkedFeatures'
import { useSettingsStore } from '@/stores/settings'
import { formatDateTime } from '@/utils/date'
import { renderMarkdown } from '@/utils/markdown'

const route = useRoute()
const router = useRouter()
const budStore = useBUDStore()
const authStore = useAuthStore()
const membersStore = useMembersStore()
const settingsStore = useSettingsStore()
const budLinkedFeaturesStore = useBudLinkedFeaturesStore()

const bud = computed(() => budStore.currentBUD)

const activeTab = ref('requirements')
const confirmDelete = ref(false)
const showNoPRWarningDialog = ref(false)

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
const closedEvent = computed(() => {
  const events = timelineEvents.value.filter(
    (e) =>
      e.event_type === 'status_change' &&
      (e.detail?.to === 'closed' || e.detail?.to === 'discarded'),
  )
  return events.length > 0 ? events[events.length - 1] : null
})
const closedReason = computed(() => {
  const evt = closedEvent.value
  return (evt?.detail?.reason as string) || null
})
const closedFrom = computed(() => {
  const evt = closedEvent.value
  return (evt?.detail?.from as string) || null
})
const closedTimelineEvents = computed(() =>
  timelineEvents.value.filter(
    (e) =>
      e.event_type === 'status_change' &&
      (e.detail?.to === 'closed' || e.detail?.to === 'discarded'),
  ),
)
const formatClosedDate = formatDateTime

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

// Pending-manual-test-cases dialog state (testing → uat/prod guard).
// Populated from bud.value.qa_manual_cases when the user attempts a
// forward transition out of testing with pending cases still open.
const showPendingCasesDialog = ref(false)
const pendingCasesTarget = ref<string>('')
const pendingCasesList = ref<{ id: string; title: string }[]>([])

// Snackbar surfaces backend PATCH failures (the store now extracts
// detail strings verbatim from 400/403/500 responses).
const statusErrorSnackbar = ref(false)
const statusErrorMessage = ref('')

// Child component refs
const designPanelRef = ref<InstanceType<typeof BUDDesignPanel> | null>(null)
const devPanelRef = ref<InstanceType<typeof BUDDevelopmentPanel> | null>(null)
const workflowRef = ref<InstanceType<typeof BUDWorkflowActions> | null>(null)

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

// Chat state
const chatOpen = ref(false)
const chatLoading = ref(false)
const chatMessages = ref<{ role: 'user' | 'ai'; text: string; userName?: string | null; images?: string[] }[]>([])
const chatStatusMessage = ref('')
const currentSessionId = ref<string | undefined>(undefined)

const { startTracking } = useJobSocket()

// File upload
const fileInput = ref<HTMLInputElement | null>(null)
const uploadSection = ref('requirements_md')

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

function enrichWithAI(): void {
  activeTab.value = 'requirements'
  chatOpen.value = true
  nextTick(() => {
    handleChatSend(
      'This BUD was imported from Jira with minimal description. '
      + 'DO NOT update the content yet. Instead, put your clarifying questions '
      + 'directly in the "reply" field and set "updated_content" to null. '
      + 'Ask me 2-3 questions about: what this feature does, who it\'s for, '
      + 'acceptance criteria, and edge cases. I will answer, then you write the PRD.',
      [],
    )
  })
}


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

// Auto-close chat panel when agent starts; reload timeline when agent finishes
watch(agentLocked, (locked, wasLocked) => {
  if (locked && chatOpen.value) chatOpen.value = false
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

async function loadChatHistory(): Promise<void> {
  if (!bud.value) return
  const section = currentSection.value
  const designId = section === 'design' && designPanelRef.value?.activeDesignTab
    ? designPanelRef.value.activeDesignTab
    : undefined
  const history = await budStore.fetchChatHistory(bud.value.id, section, designId, currentSessionId.value)
  chatMessages.value = history.map(m => ({ role: m.role, text: m.message, userName: m.user_name }))
}

function startNewSession(): void {
  currentSessionId.value = crypto.randomUUID()
  chatMessages.value = []
}

async function handleSaveTitle(title: string): Promise<void> {
  if (!bud.value) return
  await budStore.updateBUD(bud.value.id, { title })
  await loadTimeline()
}

const statusChanging = ref(false)
const statusChangeTarget = ref('')
const cancellingAgent = ref(false)

async function cancelRunningAgent(): Promise<void> {
  const taskId = bud.value?.active_agent_task?.id
  if (!taskId || !bud.value) return
  cancellingAgent.value = true
  try {
    await budStore.cancelAgentTask(bud.value.id, taskId)
  } finally {
    cancellingAgent.value = false
  }
}

const PHASE_ROLE_LABELS: Record<string, string> = {
  bud: 'product manager',
  design: 'designer',
  tech_arch: 'tech lead',
  development: 'developer',
  code_review: 'developer',
  testing: 'QA engineer',
  uat: 'product manager',
}

// Override reason dialog state
const overrideReasonDialog = ref(false)
const overrideReasonText = ref('')
const pendingOverrideStatus = ref('')

async function updateStatus(newStatus: string): Promise<void> {
  if (!bud.value) return

  // Intercept code_review transition: warn if no PRs are open
  if (newStatus === 'code_review') {
    const repoStatuses = await budStore.fetchCodeReviewStatus(bud.value.id)
    const hasOpenPR = repoStatuses.some(r => r.pr_state === 'open')
    if (!hasOpenPR) {
      showNoPRWarningDialog.value = true
      return
    }
  }

  // Manual advance code_review → testing:
  //   - If every impacted repo already has a merged PR, there's nothing to
  //     "override" — the code is approved on GitHub and we just advance
  //     straight through, same outcome as the webhook auto-transition.
  //   - Otherwise the user is bypassing PR merges (e.g. docs-only change
  //     or unusual workflow), so we still prompt for a reason so the
  //     bypass is recorded on the timeline.
  if (bud.value.status === 'code_review' && newStatus === 'testing') {
    const repoStatuses = await budStore.fetchCodeReviewStatus(bud.value.id)
    const allMerged = repoStatuses.length > 0
      && repoStatuses.every(r => r.pr_state === 'merged')
    if (!allMerged) {
      pendingOverrideStatus.value = newStatus
      overrideReasonText.value = ''
      overrideReasonDialog.value = true
      return
    }
  }

  // Guard: testing → uat (or → prod when UAT is disabled) must have
  // every manual test case in a terminal state. Preempt the backend
  // guard client-side so the user sees the list of blocking cases in a
  // modal instead of hitting a 400 and seeing a snackbar. The backend
  // guard still fires as the authoritative check.
  //
  // Re-fetch the BUD first so qa_manual_cases reflects results saved
  // in the QA tab. The test runner composable (useQATestCases) updates
  // its own local ref but doesn't refresh the store's currentBUD, so
  // bud.value.qa_manual_cases can be stale after marking cases as pass.
  if (bud.value.status === 'testing' && (newStatus === 'uat' || newStatus === 'prod')) {
    await budStore.fetchBUD(bud.value.id)
    const pending = (bud.value.qa_manual_cases ?? []).filter(
      tc => tc.result === 'pending',
    )
    if (pending.length > 0) {
      pendingCasesTarget.value = newStatus
      pendingCasesList.value = pending.map(tc => ({ id: tc.id, title: tc.title }))
      showPendingCasesDialog.value = true
      return
    }
  }

  await _executeStatusChange(newStatus)
}

function openQATab(): void {
  showPendingCasesDialog.value = false
  activeTab.value = 'testing'
}

async function confirmNoPRWarning(): Promise<void> {
  showNoPRWarningDialog.value = false
  await _executeStatusChange('code_review')
}

async function confirmOverrideStatus(): Promise<void> {
  if (!bud.value || !overrideReasonText.value.trim()) return
  overrideReasonDialog.value = false
  await _executeStatusChange(pendingOverrideStatus.value, overrideReasonText.value.trim())
}

async function _executeStatusChange(newStatus: string, reason?: string): Promise<void> {
  if (!bud.value) return
  statusChangeTarget.value = newStatus
  statusChanging.value = true
  try {
    const payload: Record<string, unknown> = { status: newStatus }
    if (reason) payload.status_override_reason = reason
    const result = await budStore.updateBUD(bud.value.id, payload as never)
    // When the store returns null, the backend rejected the PATCH. The
    // store has already captured the detail string into budStore.error
    // via extractApiError — surface it in the snackbar so the user sees
    // exactly why (e.g. the backend manual-cases guard catching a race
    // the client-side preempt missed).
    if (result === null && budStore.error) {
      statusErrorMessage.value = budStore.error
      statusErrorSnackbar.value = true
      return
    }
  } finally {
    statusChanging.value = false
  }

  // Switch tab to match the new status phase
  const targetTab = STATUS_TAB_MAP[newStatus]
  if (targetTab) activeTab.value = targetTab

  // If entering design phase, open repo picker for generation
  if (budStore.designAvailable) {
    budStore.designAvailable = false
    await nextTick()
    designPanelRef.value?.triggerDesignGeneration()
  }

  await loadTimeline()
}

// Unified toggle for whichever tab is active
function toggleEdit(): void {
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

// ── Chat ──────────────────────────────────────────────

async function handleChatSend(msg: string, images: string[] = []): Promise<void> {
  if (!bud.value || chatLoading.value) return

  chatMessages.value.push({ role: 'user', text: msg, images: images.length ? images : undefined })
  chatLoading.value = true
  chatStatusMessage.value = ''

  const chatDesignId = currentSection.value === 'design' && designPanelRef.value?.activeDesignTab
    ? designPanelRef.value.activeDesignTab
    : undefined
  const result = await budStore.chatBUD(bud.value.id, msg, currentSection.value, chatDesignId, currentSessionId.value, images)
  if (!result) {
    chatMessages.value.push({ role: 'ai', text: 'Sorry, something went wrong. Please try again.' })
    chatLoading.value = false
    return
  }

  // Persist the server-generated session_id so the next message in this
  // thread carries it forward — that's what lets the worker pass
  // --resume <id> and hit the Anthropic prompt cache on iteration 2+.
  if (result.sessionId) currentSessionId.value = result.sessionId

  startTracking(result.jobId, {
    onProgress(status) {
      chatStatusMessage.value = status.statusMessage
    },
    async onComplete(data) {
      chatLoading.value = false
      const result = (data as unknown as Record<string, unknown>).result as { reply: string; updated_content: string | null } | null
      const reply = result?.reply || ''
      const updated_content = result?.updated_content ?? null
      if (reply) chatMessages.value.push({ role: 'ai', text: reply })
      if (updated_content !== null) {
        if (budStore.currentBUD) {
          (budStore.currentBUD as Record<string, unknown>)[currentSection.value] = updated_content
        }
        if (currentSection.value === 'requirements_md' && editingContent.value) {
          editContent.value = updated_content
        } else if (currentSection.value === 'tech_spec_md' && editingTechSpec.value) {
          editTechSpec.value = updated_content
        } else if (currentSection.value === 'design') {
          if (bud.value) await designPanelRef.value?.loadDesigns()
          designPanelRef.value?.refreshDesignPreview()
        }
      }
      // Linked-features refetch is handled by the agentLocked watcher
      // (universal hook for any PM run, not just the chat-job path).
    },
    onError(err, errorCode) {
      chatLoading.value = false
      chatMessages.value.push({
        role: 'ai',
        text: friendlyAgentError(errorCode, err).headline,
      })
    },
  })
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

function triggerUpload(section: string): void {
  uploadSection.value = section
  fileInput.value?.click()
}

async function handleFileUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || !bud.value) return

  await budStore.importBUD(bud.value.id, uploadSection.value, file)
  input.value = ''
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
/* ── Pending cases dialog ────────────────────── */
.pending-cases-list {
  max-height: 240px;
  overflow-y: auto;
  padding: 8px 12px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 6px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.pending-case-row {
  display: flex;
  align-items: center;
  font-size: 13px;
  padding: 3px 0;
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.pending-case-row .text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}

/* ── Agent banner ────────────────────────────── */
.agent-banner {
  padding: 10px 16px;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-theme-primary), 0.25);
  background: rgba(var(--v-theme-primary), 0.06);
}

.agent-banner__text {
  min-width: 0;
}

.agent-banner__progress {
  max-width: 120px;
}

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

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-right: 4px;
}

.toolbar-actions .v-btn {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
  font-size: 12px;
}

.toolbar-sep {
  width: 1px;
  height: 18px;
  background: rgba(var(--v-theme-on-surface), 0.12);
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

<style src="@/components/buds/bud-section.css"></style>
