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
          <div class="d-flex align-start ga-3 mb-1">
            <v-btn icon="mdi-arrow-left" variant="text" size="small" class="mt-1" @click="$router.push('/buds')" />
            <div class="flex-grow-1">
              <div class="d-flex align-center ga-2 mb-1 flex-wrap">
                <span class="text-caption text-medium-emphasis">
                  BUD-{{ String(bud.bud_number).padStart(3, '0') }}
                </span>
                <v-chip
                  :color="statusColor"
                  variant="tonal"
                  size="x-small"
                  label
                >
                  {{ BUD_STATUS_LABELS[bud.status] }}
                </v-chip>
                <v-menu location="bottom">
                  <template #activator="{ props: assigneeProps }">
                    <v-chip
                      v-bind="assigneeProps"
                      :color="bud.assignee_name ? 'teal' : 'default'"
                      variant="tonal"
                      size="x-small"
                      label
                      class="cursor-pointer"
                    >
                      <v-icon start size="12">{{ bud.assignee_name ? 'mdi-account' : 'mdi-account-outline' }}</v-icon>
                      {{ bud.assignee_name || 'Unassigned' }}
                    </v-chip>
                  </template>
                  <v-card min-width="240" max-width="300" class="pa-2">
                    <v-text-field
                      v-model="assigneeSearch"
                      variant="outlined"
                      density="compact"
                      placeholder="Search members..."
                      hide-details
                      prepend-inner-icon="mdi-magnify"
                      class="mb-1"
                    />
                    <v-list density="compact" max-height="240" class="overflow-y-auto">
                      <v-list-item
                        v-if="bud.assignee_id"
                        density="compact"
                        @click="handleAssigneeChange(null)"
                      >
                        <template #prepend>
                          <v-icon size="18" color="error">mdi-account-remove</v-icon>
                        </template>
                        <v-list-item-title class="text-caption">Unassign</v-list-item-title>
                      </v-list-item>
                      <v-list-item
                        v-for="m in membersStore.members.filter(
                          mm => mm.isActive && mm.name.toLowerCase().includes(assigneeSearch.toLowerCase())
                        )"
                        :key="m.id"
                        :active="bud.assignee_id === m.id"
                        density="compact"
                        @click="handleAssigneeChange(m.id)"
                      >
                        <template #prepend>
                          <v-avatar size="24" color="surface-variant" class="mr-2">
                            <span class="text-caption">{{ m.name.charAt(0).toUpperCase() }}</span>
                          </v-avatar>
                        </template>
                        <v-list-item-title class="text-caption">{{ m.name }}</v-list-item-title>
                        <v-list-item-subtitle class="text-caption">{{ m.role }}</v-list-item-subtitle>
                      </v-list-item>
                    </v-list>
                  </v-card>
                </v-menu>
                <v-menu>
                  <template #activator="{ props: menuProps }">
                    <v-btn v-bind="menuProps" icon="mdi-dots-vertical" variant="text" size="x-small" />
                  </template>
                  <v-list density="compact" min-width="180">
                    <v-list-subheader>Change Status</v-list-subheader>
                    <v-list-item
                      v-for="s in statusItems"
                      :key="s.value"
                      :title="s.title"
                      :active="bud.status === s.value"
                      :disabled="agentLocked"
                      @click="updateStatus(s.value)"
                    />
                    <v-divider class="my-1" />
                    <v-list-item
                      base-color="error"
                      class="delete-item"
                      :disabled="agentLocked"
                      @click="confirmDelete = true"
                    >
                      <div class="d-flex align-center">
                        <v-icon icon="mdi-delete-outline" size="18" class="mr-2" />
                        Delete BUD
                      </div>
                    </v-list-item>
                  </v-list>
                </v-menu>
                <v-btn
                  :variant="chatOpen ? 'flat' : 'tonal'"
                  :color="chatOpen ? 'primary' : 'default'"
                  size="x-small"
                  class="ai-chat-btn"
                  :disabled="agentLocked"
                  @click="chatOpen = !chatOpen"
                >
                  <v-icon start size="14">mdi-creation-outline</v-icon>
                  AI
                </v-btn>
              </div>
              <div
                v-if="!editingTitle"
                class="text-h5 font-weight-bold"
                :class="agentLocked ? 'prd-locked-title' : 'cursor-pointer'"
                @click="startEditTitle"
              >
                {{ bud.title }}
              </div>
              <v-text-field
                v-else
                v-model="editTitle"
                variant="outlined"
                density="compact"
                autofocus
                hide-details
                class="mt-1"
                style="max-width: 500px;"
                @blur="saveTitle"
                @keyup.enter="saveTitle"
                @keyup.escape="editingTitle = false"
              />
            </div>
          </div>

          <div class="text-caption text-medium-emphasis mb-3 ml-12">
            Created {{ formatDate(bud.created_at) }} &middot; Updated {{ formatDate(bud.updated_at) }}
          </div>

          <!-- Workflow banners, code review panel, approval/reject/reassign dialogs -->
          <BUDWorkflowActions
            ref="workflowRef"
            :bud="bud"
            :can-approve="canApprove"
            :is-current-assignee="isCurrentAssignee"
            @status-change="updateStatus"
            @reload-timeline="loadTimeline(); loadEstimates()"
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
            </v-tabs>
            <div v-if="activeTab !== 'development' && activeTab !== 'code-review' && activeTab !== 'testing'" class="toolbar-actions">
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
                <textarea
                  v-if="editingContent"
                  v-model="editContent"
                  class="section-editor"
                  placeholder="Write requirements in markdown..."
                  @blur="saveContent"
                />
                <div
                  v-else-if="bud.requirements_md"
                  class="rendered-markdown"
                  v-html="renderMarkdown(bud.requirements_md)"
                />
                <div v-else class="section-empty">
                  <v-icon icon="mdi-text-box-outline" size="40" class="mb-3" />
                  <div>No requirements written yet</div>
                  <v-btn variant="tonal" size="small" class="mt-3" @click="toggleContentEdit">
                    <v-icon start size="15">mdi-pencil-outline</v-icon>
                    Start writing
                  </v-btn>
                </div>
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
                <div class="pa-4">
                  <!-- Agent running state -->
                  <div v-if="workflowRef?.agentGenerating && bud.status === 'code_review'" class="d-flex justify-center py-12">
                    <v-progress-circular indeterminate size="24" width="2" class="mr-3" />
                    <span class="text-body-2 text-medium-emphasis">{{ workflowRef?.agentStatusMessage || 'Reviewing code...' }}</span>
                  </div>

                  <!-- Empty state: not in code_review yet -->
                  <div v-else-if="bud.status !== 'code_review' && bud.status !== 'testing' && bud.status !== 'uat' && bud.status !== 'prod' && bud.status !== 'closed'" class="text-center py-12">
                    <v-icon icon="mdi-code-tags-check" size="48" color="primary" class="mb-3 opacity-40" />
                    <div class="text-h6 font-weight-medium mb-2">Code review not started</div>
                    <div class="text-body-2 text-medium-emphasis">
                      Code review will begin when development is complete and moved to the code review stage.
                    </div>
                  </div>

                  <!-- Completed state: already past code review -->
                  <div v-else-if="bud.status !== 'code_review'" class="text-center py-8">
                    <v-icon icon="mdi-check-circle-outline" size="48" color="success" class="mb-3 opacity-60" />
                    <div class="text-body-1 font-weight-medium">Code review completed</div>
                  </div>

                  <!-- Active code review: show checklist -->
                  <template v-else>
                    <!-- Toolbar: Download + Add Manual Comment -->
                    <div class="d-flex align-center mb-3 ga-2">
                      <v-icon start size="18">mdi-clipboard-check-outline</v-icon>
                      <span class="text-subtitle-1 font-weight-medium">
                        Code Review ({{ workflowRef?.resolvedCount ?? 0 }}/{{ workflowRef?.codeReviewComments?.length ?? 0 }})
                      </span>
                      <v-spacer />
                      <v-progress-linear
                        v-if="workflowRef?.codeReviewComments?.length"
                        :model-value="(workflowRef.resolvedCount / workflowRef.codeReviewComments.length) * 100"
                        color="primary"
                        height="6"
                        rounded
                        style="max-width: 100px"
                      />
                      <v-btn
                        variant="tonal"
                        size="small"
                        prepend-icon="mdi-download"
                        @click="downloadCodeReview"
                      >
                        Download
                      </v-btn>
                      <v-btn
                        variant="outlined"
                        size="small"
                        prepend-icon="mdi-plus"
                        @click="showAddManualComment = true"
                      >
                        Add Comment
                      </v-btn>
                    </div>

                    <!-- Checklist -->
                    <v-list v-if="workflowRef?.codeReviewComments?.length" density="compact" class="rounded-lg border mb-3">
                      <v-list-item
                        v-for="(c, idx) in workflowRef.codeReviewComments"
                        :key="idx"
                        :class="{
                          'bg-green-lighten-5': workflowRef.resolutions[idx]?.done === true,
                          'bg-orange-lighten-5': workflowRef.resolutions[idx]?.done === false,
                        }"
                      >
                        <template #prepend>
                          <v-checkbox-btn
                            :model-value="workflowRef.resolutions[idx]?.done ?? false"
                            density="compact"
                            color="success"
                            @update:model-value="(val: boolean) => workflowRef?.updateResolution(idx, val)"
                          />
                        </template>
                        <v-list-item-title class="text-body-2">
                          <v-icon
                            :color="c.severity === 'error' ? 'error' : c.severity === 'warning' ? 'warning' : 'info'"
                            size="14"
                            class="mr-1"
                          >
                            {{ c.severity === 'error' ? 'mdi-alert-circle' : c.severity === 'warning' ? 'mdi-alert' : 'mdi-information' }}
                          </v-icon>
                          <code class="text-caption">{{ c.repo }}/{{ c.file }}:{{ c.line }}</code>
                          <v-chip v-if="c.deviates_from_spec" size="x-small" color="error" variant="tonal" class="ml-2">Spec Deviation</v-chip>
                          <v-chip v-if="c.source === 'manual'" size="x-small" color="purple" variant="tonal" class="ml-2">Manual</v-chip>
                        </v-list-item-title>
                        <v-list-item-subtitle class="text-body-2 mt-1">{{ c.comment }}</v-list-item-subtitle>

                        <div v-if="workflowRef.resolutions[idx]?.done === false" class="mt-1 ml-8">
                          <v-text-field
                            v-model="workflowRef.resolutions[idx].comment"
                            variant="outlined"
                            density="compact"
                            placeholder="Why not addressed? (required)"
                            :error="!workflowRef.resolutions[idx].comment?.trim() && workflowRef.pushAttempted"
                            hide-details="auto"
                          />
                        </div>
                      </v-list-item>
                    </v-list>

                    <!-- No agent comments yet -->
                    <div v-else class="text-center py-6 mb-3">
                      <v-icon icon="mdi-check-all" size="36" color="success" class="mb-2 opacity-60" />
                      <div class="text-body-2 text-medium-emphasis">No agent review comments. Add manual comments above.</div>
                    </div>

                    <!-- Re-review + Push to QA -->
                    <div class="d-flex align-center">
                      <span class="text-caption text-medium-emphasis">
                        Re-runs code review to verify fixes, then moves to QA if clean
                      </span>
                      <v-spacer />
                      <v-btn
                        variant="text"
                        size="small"
                        color="warning"
                        @click="skipCodeReview"
                      >
                        Skip & Push to QA
                      </v-btn>
                      <v-btn
                        color="primary"
                        variant="flat"
                        size="small"
                        class="ml-2"
                        :disabled="!workflowRef?.canPushToQA"
                        @click="workflowRef?.handlePushToQA()"
                      >
                        <v-icon start size="16">mdi-refresh</v-icon>
                        Re-review & Push to QA
                      </v-btn>
                    </div>
                  </template>

                  <!-- Add Manual Comment Dialog -->
                  <v-dialog v-model="showAddManualComment" max-width="480">
                    <v-card class="pa-2">
                      <v-card-title class="text-h6 pb-1">Add Code Review Comment</v-card-title>
                      <v-card-text class="pb-2">
                        <v-select
                          v-model="manualComment.repo"
                          variant="outlined"
                          density="compact"
                          label="Repository"
                          :items="repoDropdownItems"
                          class="mb-2"
                        />
                        <v-textarea
                          v-model="manualComment.comment"
                          variant="outlined"
                          density="compact"
                          label="Comment"
                          rows="3"
                          placeholder="Describe the issue or feedback..."
                          :rules="[v => !!v?.trim() || 'Comment is required']"
                        />
                      </v-card-text>
                      <v-card-actions class="px-4 pb-3 pt-0">
                        <v-spacer />
                        <v-btn variant="text" size="small" @click="showAddManualComment = false">Cancel</v-btn>
                        <v-btn
                          color="primary"
                          variant="flat"
                          size="small"
                          :disabled="!manualComment.comment?.trim()"
                          @click="addManualComment"
                        >
                          Add Comment
                        </v-btn>
                      </v-card-actions>
                    </v-card>
                  </v-dialog>
                </div>
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

              <!-- Test Plan tab removed — test plan content is now part of QA tab -->
            </v-tabs-window>
          </div>

          <!-- Delivery Estimates -->
          <BUDEstimateTimeline
            :estimates="budEstimates"
            :current-phase="bud.status"
            :loading="estimatesLoading"
            :recalculating="recalculating"
            @recalculate="handleRecalculate"
            @override-phase="openOverrideDialog"
            class="mt-4"
          />

          <!-- Override Dialog -->
          <v-dialog v-model="overrideDialogOpen" max-width="420">
            <v-card color="surface" class="pa-5">
              <div class="text-subtitle-1 font-weight-medium mb-3">
                Override {{ overridePhase }} deadline
              </div>
              <v-text-field
                v-model="overrideDate"
                label="New deadline"
                type="date"
                class="mb-3"
              />
              <v-textarea
                v-model="overrideReason"
                label="Reason (required)"
                rows="3"
                :rules="[v => !!v?.trim() || 'Reason is required']"
              />
              <v-card-actions class="pa-0 mt-2">
                <v-spacer />
                <v-btn variant="text" @click="overrideDialogOpen = false">Cancel</v-btn>
                <v-btn
                  color="warning"
                  variant="flat"
                  :disabled="!overrideDate || !overrideReason.trim()"
                  @click="submitOverride"
                >
                  Override
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-dialog>

          <!-- Activity Timeline (collapsible) -->
          <div class="timeline-section mt-4">
            <button class="timeline-toggle" @click="timelineOpen = !timelineOpen">
              <v-icon :icon="timelineOpen ? 'mdi-chevron-down' : 'mdi-chevron-right'" size="18" />
              <span class="text-subtitle-2 font-weight-medium">Activity</span>
              <span class="text-caption text-medium-emphasis ml-1">({{ timelineEvents.length }})</span>
            </button>
            <div v-if="timelineOpen" class="timeline-body">
              <BUDTimeline :events="timelineEvents" :loading="timelineLoading" />
            </div>
          </div>
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
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { useAuthStore } from '@/stores/auth'
import { useMembersStore } from '@/stores/members'
import { useJobSocket } from '@/composables/useJobSocket'
import { useMarkdownSection } from '@/composables/useMarkdownSection'
import { BUD_STATUS_ORDER, BUD_STATUS_LABELS, BUD_STATUS_COLORS, BUD_SECTIONS, VALID_BUD_TABS, TAB_TO_SECTION } from '@/types'
import type { BUDSectionKey, TimelineEvent } from '@/types'
import { useEstimates } from '@/composables/useEstimates'
import ChatPanel from '@/components/buds/ChatPanel.vue'
import BUDEstimateTimeline from '@/components/buds/BUDEstimateTimeline.vue'
import BUDTimeline from '@/components/buds/BUDTimeline.vue'
import BUDDesignPanel from '@/components/buds/BUDDesignPanel.vue'
import BUDDevelopmentPanel from '@/components/buds/BUDDevelopmentPanel.vue'
import BUDPRChecklist from '@/components/buds/BUDPRChecklist.vue'
import BUDQAPanel from '@/components/buds/BUDQAPanel.vue'
import BUDWorkflowActions from '@/components/buds/BUDWorkflowActions.vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const route = useRoute()
const router = useRouter()
const budStore = useBUDStore()
const authStore = useAuthStore()
const membersStore = useMembersStore()

const bud = computed(() => budStore.currentBUD)

const activeTab = ref('requirements')
const confirmDelete = ref(false)

// Child component refs
const designPanelRef = ref<InstanceType<typeof BUDDesignPanel> | null>(null)
const devPanelRef = ref<InstanceType<typeof BUDDevelopmentPanel> | null>(null)
const workflowRef = ref<InstanceType<typeof BUDWorkflowActions> | null>(null)

const canApprove = computed(() => {
  const role = authStore.user?.role
  return role === 'tech_lead' || role === 'manager' || role === 'org_owner'
})

// ── Code Review: download + manual comments ──────────────
const showAddManualComment = ref(false)
const manualComment = ref({ repo: '', comment: '' })

const repoDropdownItems = computed(() => {
  const repos = bud.value?.impacted_repos || []
  return repos.map(r => r.repo_name)
})

function downloadCodeReview(): void {
  if (!bud.value || !workflowRef.value) return
  const budRef = `BUD-${String(bud.value.bud_number).padStart(3, '0')}`
  const comments = workflowRef.value.codeReviewComments || []

  let md = `# Code Review: ${budRef} — ${bud.value.title}\n\n`
  md += `**${comments.length} comments**\n\n`
  for (const c of comments) {
    const tag = c.severity === 'error' ? '[ERROR]' : c.severity === 'warning' ? '[WARN]' : '[INFO]'
    const loc = c.file ? `${c.repo}/${c.file}:${c.line}` : c.repo
    md += `### ${tag} ${loc}\n\n${c.comment}\n\n`
    if (c.deviates_from_spec) md += `> Spec deviation\n\n`
    md += `---\n\n`
  }

  const blob = new Blob([md], { type: 'text/markdown' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${budRef}-code-review.md`
  a.click()
  URL.revokeObjectURL(a.href)
}

async function skipCodeReview(): Promise<void> {
  if (!bud.value) return
  const meta = { ...(bud.value.metadata || {}) } as Record<string, unknown>
  meta.code_review_skipped = true
  await budStore.updateBUD(bud.value.id, { metadata: meta, status: 'testing' } as never)
  await budStore.fetchBUD(bud.value.id)
}

async function addManualComment(): Promise<void> {
  if (!bud.value || !manualComment.value.comment.trim()) return

  const meta = { ...(bud.value.metadata || {}) } as Record<string, unknown>
  const comments = [...((meta.code_review_comments as Array<Record<string, unknown>>) || [])]
  comments.push({
    repo: manualComment.value.repo || 'general',
    file: '',
    line: 0,
    severity: 'warning',
    comment: manualComment.value.comment,
    deviates_from_spec: false,
    source: 'manual',
  })
  meta.code_review_comments = comments
  await budStore.updateBUD(bud.value.id, { metadata: meta } as never)
  await budStore.fetchBUD(bud.value.id)

  manualComment.value = { repo: '', comment: '' }
  showAddManualComment.value = false
}

const isCurrentAssignee = computed(() =>
  bud.value?.assignee_id != null && authStore.user?.id === bud.value.assignee_id,
)

// Timeline + assignee state
const timelineEvents = ref<TimelineEvent[]>([])
const timelineLoading = ref(false)
const timelineOpen = ref(false)
const assigneeSearch = ref('')

// Estimation (composable)
const {
  budEstimates, estimatesLoading, recalculating,
  overrideDialogOpen, overridePhase, overrideDate, overrideReason,
  loadEstimates, handleRecalculate, openOverrideDialog, submitOverride,
} = useEstimates(() => bud.value?.id)

// Title editing
const editingTitle = ref(false)
const editTitle = ref('')

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

const statusItems = BUD_STATUS_ORDER.map(s => ({
  title: BUD_STATUS_LABELS[s],
  value: s,
}))

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
  return !!t && (t.status === 'pending' || t.status === 'running')
})

// ── Markdown rendering ────────────────────────────────
function renderMarkdown(md: string | null): string {
  if (!md) return ''
  const raw = marked.parse(md, { async: false }) as string
  return DOMPurify.sanitize(raw)
}

onMounted(async () => {
  const tabParam = route.query.tab as string | undefined
  if (tabParam && VALID_BUD_TABS.has(tabParam)) {
    activeTab.value = tabParam
  }

  const id = route.params.id as string
  await budStore.fetchBUD(id)

  // Auto-select tab based on BUD status (unless explicit ?tab= param)
  if (!tabParam && bud.value) {
    const statusTabMap: Record<string, string> = {
      design: 'design',
      tech_arch: 'tech-spec',
      development: 'development',
      code_review: 'code-review',
      testing: 'testing',
    }
    const defaultTab = statusTabMap[bud.value.status]
    if (defaultTab) activeTab.value = defaultTab
  }

  await loadChatHistory()
  membersStore.fetchMembers()
  loadTimeline()
  loadEstimates()
})

// Track active agent task. Watches both the task data and the component ref
// so tracking starts as soon as both are available (covers any mount order).
watch(
  [() => bud.value?.active_agent_task, workflowRef],
  ([task, wf]) => {
    if (!task?.job_id || (task.status !== 'pending' && task.status !== 'running')) return
    if (wf) wf.trackAgentTask(task)
  },
  { immediate: true },
)

// Auto-close chat panel when agent starts; reload timeline when agent finishes
watch(agentLocked, (locked, wasLocked) => {
  if (locked && chatOpen.value) chatOpen.value = false
  if (!locked && wasLocked) {
    loadTimeline()
    loadEstimates()
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

function startEditTitle(): void {
  if (agentLocked.value) return
  editTitle.value = bud.value?.title || ''
  editingTitle.value = true
}

async function saveTitle(): Promise<void> {
  if (!bud.value || !editTitle.value.trim()) {
    editingTitle.value = false
    return
  }
  if (editTitle.value.trim() !== bud.value.title) {
    await budStore.updateBUD(bud.value.id, { title: editTitle.value.trim() })
    await loadTimeline()
  }
  editingTitle.value = false
}

const statusChanging = ref(false)
const statusChangeTarget = ref('')

const PHASE_ROLE_LABELS: Record<string, string> = {
  bud: 'product manager',
  design: 'designer',
  tech_arch: 'tech lead',
  development: 'developer',
  code_review: 'reviewer',
  testing: 'QA engineer',
  uat: 'product manager',
}

async function updateStatus(newStatus: string): Promise<void> {
  if (!bud.value) return

  // Intercept code_review transition to show repo confirmation
  // Skip the popup if code review content already exists (e.g. going back from QA)
  if (newStatus === 'code_review') {
    const meta = bud.value.metadata as Record<string, unknown> | undefined
    const hasCodeReview = Array.isArray(meta?.code_review_comments)
      && (meta.code_review_comments as unknown[]).length > 0
    if (!hasCodeReview) {
      await workflowRef.value?.showCodeReviewConfirmation()
      return
    }
  }

  statusChangeTarget.value = newStatus
  statusChanging.value = true
  try {
    await budStore.updateBUD(bud.value.id, { status: newStatus } as never)
  } finally {
    statusChanging.value = false
  }

  // Switch tab to match the new status phase
  const STATUS_TO_TAB: Record<string, string> = {
    bud: 'requirements',
    design: 'design',
    tech_arch: 'tech-spec',
    development: 'development',
    code_review: 'code-review',
    testing: 'testing',
  }
  const targetTab = STATUS_TO_TAB[newStatus]
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

  startTracking(result.jobId, {
    onProgress(status) {
      chatStatusMessage.value = status.statusMessage
    },
    async onComplete(data) {
      chatLoading.value = false
      const { reply, updated_content } = data as unknown as { reply: string; updated_content: string | null }
      chatMessages.value.push({ role: 'ai', text: reply })
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
    },
    onError(err) {
      chatLoading.value = false
      chatMessages.value.push({ role: 'ai', text: `Error: ${err}` })
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

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
</script>

<style scoped>
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
  max-width: 960px;
}

.bud-main.chat-open .bud-page-content {
  max-width: none;
}

/* ── AI Chat button ────────────────────────────── */
.ai-chat-btn {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
  font-size: 13px;
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

/* ── Editor ────────────────────────────────────── */
.section-editor {
  display: block;
  width: 100%;
  min-height: 450px;
  padding: 24px 28px;
  border: none;
  outline: none;
  resize: vertical;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.87);
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
  font-size: 13px;
  line-height: 1.75;
  box-sizing: border-box;
}

/* ── Rendered Markdown ─────────────────────────── */
.rendered-markdown {
  padding: 24px 28px;
  line-height: 1.75;
  color: rgba(var(--v-theme-on-surface), 0.87);
  font-size: 14px;
}

.rendered-markdown :deep(h1) {
  font-size: 1.5em;
  font-weight: 700;
  margin: 0 0 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  color: rgba(var(--v-theme-on-surface), 0.95);
}

.rendered-markdown :deep(h2) {
  font-size: 1.2em;
  font-weight: 600;
  margin: 28px 0 10px;
  color: rgba(var(--v-theme-on-surface), 0.92);
}

.rendered-markdown :deep(h3) {
  font-size: 1.05em;
  font-weight: 600;
  margin: 22px 0 8px;
  color: rgba(var(--v-theme-on-surface), 0.88);
}

.rendered-markdown :deep(p) {
  margin: 0 0 14px;
}

.rendered-markdown :deep(ul),
.rendered-markdown :deep(ol) {
  margin: 0 0 14px;
  padding-left: 24px;
}

.rendered-markdown :deep(li) {
  margin-bottom: 5px;
}

.rendered-markdown :deep(li p) {
  margin: 0;
}

.rendered-markdown :deep(strong) {
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.95);
}

.rendered-markdown :deep(em) {
  font-style: italic;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

.rendered-markdown :deep(code) {
  background: rgba(var(--v-theme-on-surface), 0.07);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.87em;
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, monospace;
}

.rendered-markdown :deep(pre) {
  background: rgba(var(--v-theme-on-surface), 0.05);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 6px;
  padding: 14px 18px;
  margin: 0 0 14px;
  overflow-x: auto;
}

.rendered-markdown :deep(pre code) {
  background: none;
  padding: 0;
  font-size: 13px;
}

.rendered-markdown :deep(blockquote) {
  border-left: 3px solid rgba(var(--v-theme-primary), 0.4);
  padding-left: 16px;
  margin: 0 0 14px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.rendered-markdown :deep(hr) {
  border: none;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  margin: 24px 0;
}

.rendered-markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 14px;
  font-size: 13px;
}

.rendered-markdown :deep(th),
.rendered-markdown :deep(td) {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  padding: 8px 12px;
  text-align: left;
}

.rendered-markdown :deep(th) {
  background: rgba(var(--v-theme-on-surface), 0.04);
  font-weight: 600;
}

.rendered-markdown :deep(a) {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}

.rendered-markdown :deep(a:hover) {
  text-decoration: underline;
}

/* ── Empty state ───────────────────────────────── */
.section-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px;
  color: rgba(var(--v-theme-on-surface), 0.35);
  font-size: 14px;
}

.section-empty .v-icon {
  opacity: 0.35;
}

/* ── Timeline section ──────────────────────────── */
.timeline-section {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
}

.timeline-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 10px 14px;
  background: none;
  border: none;
  cursor: pointer;
  color: rgba(var(--v-theme-on-surface), 0.87);
  text-align: left;
}

.timeline-toggle:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 8px;
}

.timeline-body {
  padding: 0 14px 14px;
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

/* ── PRD lock state ───────────────────────────── */
.prd-locked-title {
  opacity: 0.5;
  pointer-events: none;
}
</style>
