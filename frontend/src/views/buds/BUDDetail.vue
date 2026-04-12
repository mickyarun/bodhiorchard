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
                      v-if="isClosed"
                      disabled
                    >
                      <span class="text-caption text-medium-emphasis">
                        {{ bud.status === 'discarded' ? 'Discarded' : 'Closed' }} — cannot change status
                      </span>
                    </v-list-item>
                    <template v-else>
                      <v-list-item
                        v-for="s in statusItems"
                        :key="s.value"
                        :title="s.title"
                        :active="bud.status === s.value"
                        :disabled="agentLocked"
                        @click="updateStatus(s.value)"
                      />
                    </template>
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

          <!-- Workflow banners, approval/reject/reassign dialogs, repo confirmation -->
          <BUDWorkflowActions
            ref="workflowRef"
            :bud="bud"
            :can-approve="canApprove"
            :is-current-assignee="isCurrentAssignee"
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
          <BUDEstimateTimeline
            v-if="!isClosed"
            :estimates="budEstimates"
            :current-phase="bud.status"
            :loading="estimatesLoading"
            :recalculating="recalculating"
            @recalculate="handleRecalculate"
            @override-phase="openOverrideDialog"
            class="mt-4"
          />

          <!-- Linked Bugs -->
          <v-card variant="outlined" class="mt-4 pa-4">
            <div class="d-flex align-center mb-3">
              <v-icon icon="mdi-bug-outline" size="20" class="mr-2" />
              <span class="text-subtitle-2 font-weight-medium">Bugs</span>
              <v-chip v-if="budBugs.length" size="x-small" variant="tonal" color="error" class="ml-2">
                {{ budBugs.length }}
              </v-chip>
              <v-spacer />
              <v-btn
                variant="tonal"
                size="small"
                color="error"
                prepend-icon="mdi-bug-outline"
                @click="showBugCreate = true"
              >
                Report Bug
              </v-btn>
            </div>

            <div v-if="budBugsLoading" class="d-flex justify-center py-4">
              <v-progress-circular indeterminate size="20" width="2" />
            </div>
            <div v-else-if="budBugs.length === 0" class="text-caption text-medium-emphasis text-center py-2">
              No bugs linked to this BUD
            </div>
            <div v-else class="d-flex flex-column ga-1">
              <div
                v-for="bug in budBugs"
                :key="bug.id"
                class="d-flex align-center ga-2 pa-2 rounded"
                style="border: 1px solid rgba(255,255,255,0.06); cursor: pointer"
                @click="$router.push('/bugs')"
              >
                <v-chip :color="BUG_SEVERITY_COLORS[bug.severity]" size="x-small" variant="tonal">
                  {{ bug.severity }}
                </v-chip>
                <span class="text-body-2 flex-grow-1 text-truncate">{{ bug.title }}</span>
                <v-chip :color="BUG_STATUS_COLORS[bug.status]" size="x-small" variant="tonal">
                  {{ bug.status }}
                </v-chip>
              </div>
            </div>
          </v-card>

          <BugCreateDialog
            v-model="showBugCreate"
            :bud-id="bud.id"
            @created="onBugCreated"
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
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { useAuthStore } from '@/stores/auth'
import { useMembersStore } from '@/stores/members'
import { useJobSocket } from '@/composables/useJobSocket'
import { subscribe, unsubscribe } from '@/services/socket'
import { useMarkdownSection } from '@/composables/useMarkdownSection'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import { BUD_STATUS_ORDER, BUD_STATUS_LABELS, BUD_STATUS_COLORS, BUG_SEVERITY_COLORS, BUG_STATUS_COLORS, BUD_SECTIONS, VALID_BUD_TABS, TAB_TO_SECTION } from '@/types'
import type { BUDSectionKey, BUDStatus, TimelineEvent } from '@/types'
import { useEstimates } from '@/composables/useEstimates'
import ChatPanel from '@/components/buds/ChatPanel.vue'
import BUDEstimateTimeline from '@/components/buds/BUDEstimateTimeline.vue'
import BUDTimeline from '@/components/buds/BUDTimeline.vue'
import BUDDesignPanel from '@/components/buds/BUDDesignPanel.vue'
import BUDDevelopmentPanel from '@/components/buds/BUDDevelopmentPanel.vue'
import BUDPRChecklist from '@/components/buds/BUDPRChecklist.vue'
import BUDCodeReviewStatus from '@/components/buds/BUDCodeReviewStatus.vue'
import BUDQAPanel from '@/components/buds/BUDQAPanel.vue'
import BUDReleaseStagePanel from '@/components/buds/BUDReleaseStagePanel.vue'
import BugCreateDialog from '@/views/bugs/BugCreateDialog.vue'
import BUDWorkflowActions from '@/components/buds/BUDWorkflowActions.vue'
import { useBugsStore } from '@/stores/bugs'
import { useSettingsStore } from '@/stores/settings'
import { formatDateTime } from '@/utils/date'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const route = useRoute()
const router = useRouter()
const budStore = useBUDStore()
const authStore = useAuthStore()
const membersStore = useMembersStore()
const settingsStore = useSettingsStore()
const bugsStore = useBugsStore()

// Bugs linked to this BUD
const budBugs = ref<import('@/types').BugListItem[]>([])
const budBugsLoading = ref(false)
const showBugCreate = ref(false)

async function loadBudBugs(): Promise<void> {
  if (!bud.value) return
  budBugsLoading.value = true
  budBugs.value = await bugsStore.fetchBugsForBud(bud.value.id)
  budBugsLoading.value = false
}

function onBugCreated(): void {
  loadBudBugs()
}

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
    const defaultTab = STATUS_TAB_MAP[bud.value.status]
    if (defaultTab) activeTab.value = defaultTab
  }

  await loadChatHistory()
  membersStore.fetchMembers()
  loadTimeline()
  loadEstimates()
  // Settings store powers the UAT toggle visibility (uatStageEnabled)
  // and the release-stage panels' "configure branch" CTA
  // (hasUatBranchConfigured / hasMainBranchConfigured). Both actions
  // are no-ops if the data is already cached, so this is cheap.
  if (!settingsStore.connections.budStages) settingsStore.fetchConnections()
  if (settingsStore.repos.length === 0) settingsStore.fetchRepos()
  loadBudBugs()

  // Subscribe to BUD activity events (PR opened/merged/comment via webhook)
  const budActivityTopic = `bud:${id}:activity`
  const handleBudActivity = () => {
    budStore.fetchBUD(id)
    loadTimeline()
    loadEstimates()
  }
  subscribe(budActivityTopic, handleBudActivity)
  onUnmounted(() => unsubscribe(budActivityTopic, handleBudActivity))
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
