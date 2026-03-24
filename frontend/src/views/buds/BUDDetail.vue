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
          <div class="d-flex align-center ga-3 mb-1">
            <v-btn icon="mdi-arrow-left" variant="text" size="small" @click="$router.push('/buds')" />
            <div class="flex-grow-1">
              <div class="text-caption text-medium-emphasis">
                BUD-{{ String(bud.bud_number).padStart(3, '0') }}
              </div>
              <div v-if="!editingTitle" class="text-h5 font-weight-bold cursor-pointer" @click="startEditTitle">
                {{ bud.title }}
                <v-icon icon="mdi-pencil-outline" size="16" class="ml-1 text-medium-emphasis" />
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
            <v-chip
              :color="statusColor"
              variant="tonal"
              size="small"
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
                  size="small"
                  label
                  class="cursor-pointer"
                >
                  <v-icon start size="14">{{ bud.assignee_name ? 'mdi-account' : 'mdi-account-outline' }}</v-icon>
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
                <v-btn v-bind="menuProps" icon="mdi-dots-vertical" variant="text" size="small" />
              </template>
              <v-list density="compact" min-width="180">
                <v-list-subheader>Change Status</v-list-subheader>
                <v-list-item
                  v-for="s in statusItems"
                  :key="s.value"
                  :title="s.title"
                  :active="bud.status === s.value"
                  @click="updateStatus(s.value)"
                />
                <v-divider class="my-1" />
                <v-list-item
                  base-color="error"
                  class="delete-item"
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
              size="small"
              class="ai-chat-btn"
              @click="chatOpen = !chatOpen"
            >
              <v-icon start size="16">mdi-creation-outline</v-icon>
              AI
            </v-btn>
          </div>

          <div class="text-caption text-medium-emphasis mb-3 ml-12">
            Created {{ formatDate(bud.created_at) }} &middot; Updated {{ formatDate(bud.updated_at) }}
          </div>

          <!-- Tech Arch Generating Banner -->
          <v-alert
            v-if="bud.status === 'tech_arch' && techArchGenerating"
            type="info"
            variant="tonal"
            class="mx-12 mb-3"
          >
            <div class="d-flex align-center ga-2">
              <v-progress-circular indeterminate size="18" width="2" class="mr-2" />
              <div class="flex-grow-1">
                <strong>Generating Tech Architecture...</strong>
                <div class="text-caption text-medium-emphasis">{{ techArchStatusMessage || 'Claude is analyzing your requirements and designing the implementation plan...' }}</div>
              </div>
            </div>
          </v-alert>

          <!-- Tech Architecture Approval Bar -->
          <v-alert
            v-if="bud.status === 'tech_arch' && canApprove && !!bud.tech_spec_md && !techArchGenerating"
            type="info"
            variant="tonal"
            class="mx-12 mb-3"
          >
            <div class="d-flex align-center ga-2">
              <div class="flex-grow-1">
                <strong>Tech Architecture Review</strong>
                <span v-if="awaitingManagerApproval"> — Awaiting manager approval</span>
                <span v-else> — Review the tech spec and approve or reject</span>
              </div>
              <v-btn
                color="success"
                variant="flat"
                size="small"
                :loading="approvingTechArch"
                :disabled="approvingTechArch"
                @click="handleApproveTechArch"
              >
                <v-icon start size="16">mdi-check</v-icon>
                Approve
              </v-btn>
              <v-btn
                color="error"
                variant="tonal"
                size="small"
                :disabled="approvingTechArch"
                @click="showRejectDialog = true"
              >
                <v-icon start size="16">mdi-close</v-icon>
                Reject
              </v-btn>
            </div>
          </v-alert>

          <!-- Reassignment Button (development phase, current assignee only) -->
          <v-alert
            v-if="bud.status === 'development' && isCurrentAssignee"
            type="warning"
            variant="tonal"
            class="mx-12 mb-3"
          >
            <div class="d-flex align-center ga-2">
              <div class="flex-grow-1">
                Need to hand this off? Request reassignment to another developer.
              </div>
              <v-btn variant="tonal" size="small" @click="showReassignDialog = true">
                <v-icon start size="16">mdi-swap-horizontal</v-icon>
                Request Reassignment
              </v-btn>
            </div>
          </v-alert>

          <!-- Code Review Generating Banner -->
          <v-alert
            v-if="bud.status === 'code_review' && codeReviewGenerating"
            type="info"
            variant="tonal"
            class="mx-12 mb-3"
          >
            <div class="d-flex align-center ga-2">
              <v-progress-circular indeterminate size="18" width="2" class="mr-2" />
              <div class="flex-grow-1">
                <strong>Running Code Review...</strong>
                <div class="text-caption text-medium-emphasis">{{ codeReviewStatusMessage || 'Claude is reviewing your code changes...' }}</div>
              </div>
            </div>
          </v-alert>

          <!-- Code Review Comments Panel -->
          <v-card
            v-if="bud.status === 'code_review' && codeReviewComments.length > 0 && !codeReviewGenerating"
            variant="outlined"
            class="mx-12 mb-3"
          >
            <v-card-title class="text-subtitle-1 d-flex align-center">
              <v-icon start size="18">mdi-comment-check-outline</v-icon>
              Code Review Comments ({{ codeReviewComments.length }})
            </v-card-title>
            <v-divider />
            <v-list density="compact">
              <v-list-item
                v-for="(c, idx) in codeReviewComments"
                :key="idx"
                :class="{ 'bg-green-lighten-5': c.status === 'accepted', 'bg-grey-lighten-4': c.status === 'skipped' }"
              >
                <template #prepend>
                  <v-icon
                    :color="c.severity === 'error' ? 'error' : c.severity === 'warning' ? 'warning' : 'info'"
                    size="18"
                  >
                    {{ c.severity === 'error' ? 'mdi-alert-circle' : c.severity === 'warning' ? 'mdi-alert' : 'mdi-information' }}
                  </v-icon>
                </template>
                <v-list-item-title class="text-body-2">
                  <code class="text-caption">{{ c.repo }}/{{ c.file }}:{{ c.line }}</code>
                  <v-chip v-if="c.deviates_from_spec" size="x-small" color="error" variant="tonal" class="ml-2">Spec Deviation</v-chip>
                </v-list-item-title>
                <v-list-item-subtitle class="text-body-2 mt-1">{{ c.comment }}</v-list-item-subtitle>
                <template #append>
                  <div v-if="!c.status || c.status === 'pending'" class="d-flex ga-1">
                    <v-btn size="x-small" variant="tonal" color="success" @click="handleReviewComment(idx, 'accepted')">
                      Accept
                    </v-btn>
                    <v-btn size="x-small" variant="tonal" color="grey" @click="handleReviewComment(idx, 'skipped', 'Not applicable')">
                      Skip
                    </v-btn>
                  </div>
                  <v-chip v-else size="x-small" :color="c.status === 'accepted' ? 'success' : 'grey'" variant="tonal">
                    {{ c.status }}
                  </v-chip>
                </template>
              </v-list-item>
            </v-list>
            <v-divider />
            <v-card-actions>
              <v-spacer />
              <v-btn
                color="primary"
                variant="flat"
                size="small"
                :disabled="codeReviewComments.some(c => !c.status || c.status === 'pending')"
                @click="updateStatus('testing')"
              >
                Move to QA
                <v-icon end size="16">mdi-arrow-right</v-icon>
              </v-btn>
            </v-card-actions>
          </v-card>

          <!-- Test Plans (code_review phase) -->
          <v-expansion-panels
            v-if="bud.status === 'code_review' && (automationTestPlan || manualTestPlan) && !codeReviewGenerating"
            variant="accordion"
            class="mx-12 mb-3"
          >
            <v-expansion-panel v-if="automationTestPlan">
              <v-expansion-panel-title>
                <v-icon start size="18">mdi-test-tube</v-icon>
                Automation Test Plan
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <div class="markdown-body" v-html="renderMarkdown(automationTestPlan)" />
              </v-expansion-panel-text>
            </v-expansion-panel>
            <v-expansion-panel v-if="manualTestPlan">
              <v-expansion-panel-title>
                <v-icon start size="18">mdi-clipboard-check-outline</v-icon>
                Manual Test Plan
              </v-expansion-panel-title>
              <v-expansion-panel-text>
                <div class="markdown-body" v-html="renderMarkdown(manualTestPlan)" />
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>

          <!-- Tabs + Toolbar row -->
          <div class="tabs-toolbar-row">
            <v-tabs v-model="activeTab" color="primary" density="compact">
              <v-tab value="requirements">Requirements</v-tab>
              <v-tab value="design">Design</v-tab>
              <v-tab value="tech-spec">Tech Spec</v-tab>
              <v-tab value="test-plan">Test Plan</v-tab>
            </v-tabs>
            <div class="toolbar-actions">
              <v-btn
                variant="text"
                size="small"
                class="toolbar-btn"
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
                <!-- PRD generating banner -->
                <v-alert
                  v-if="prdGenerating"
                  type="info"
                  variant="tonal"
                  density="compact"
                  class="mb-3"
                >
                  <div class="d-flex align-center ga-2">
                    <v-progress-circular indeterminate size="16" width="2" />
                    <span>{{ prdStatusMessage || 'PRD agent is enriching requirements...' }}</span>
                  </div>
                </v-alert>
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
                <!-- Multi-design sub-tabs when designs exist -->
                <div v-if="designs.length > 0" class="design-multi-panel">
                  <div class="design-sub-tabs-row">
                    <v-tabs v-model="activeDesignTab" density="compact" color="teal" class="design-sub-tabs">
                      <v-tab v-for="d in designs" :key="d.id" :value="d.id">
                        {{ d.repo_name || 'Default' }}
                        <v-icon
                          v-if="d.status === 'generating'"
                          icon="mdi-loading"
                          size="14"
                          class="ml-1 mdi-spin"
                        />
                        <v-icon
                          v-else-if="d.status === 'failed'"
                          icon="mdi-alert-circle-outline"
                          size="14"
                          class="ml-1"
                          color="error"
                        />
                      </v-tab>
                    </v-tabs>
                    <div class="d-flex align-center ga-1">
                      <v-btn
                        v-if="activeDesignObj?.status === 'ready'"
                        variant="text"
                        size="small"
                        title="Open in new tab"
                        @click="openDesignInTab(activeDesignTab)"
                      >
                        <v-icon size="15">mdi-open-in-new</v-icon>
                      </v-btn>
                      <v-btn
                        v-if="activeDesignObj?.status === 'ready'"
                        variant="text"
                        size="small"
                        title="Refresh preview"
                        @click="refreshDesignPreview()"
                      >
                        <v-icon size="15">mdi-refresh</v-icon>
                      </v-btn>
                      <v-btn
                        variant="text"
                        size="small"
                        @click="triggerDesignGeneration"
                      >
                        <v-icon size="15" class="mr-1">mdi-plus</v-icon>
                        Add
                      </v-btn>
                    </div>
                  </div>

                  <v-tabs-window v-model="activeDesignTab">
                    <v-tabs-window-item v-for="d in designs" :key="d.id" :value="d.id">
                      <!-- Generating -->
                      <div v-if="d.status === 'generating'" class="section-empty">
                        <v-progress-circular indeterminate color="secondary" size="40" class="mb-3" />
                        <div>{{ designJobProgress.get(d.id) || 'Generating wireframe...' }}</div>
                        <div class="text-caption text-medium-emphasis mt-1">
                          Using {{ d.repo_name || 'default' }} design system
                        </div>
                      </div>
                      <!-- Failed -->
                      <div v-else-if="d.status === 'failed'" class="section-empty">
                        <v-icon icon="mdi-alert-circle-outline" size="40" class="mb-3" color="error" />
                        <div>Design generation failed</div>
                        <v-btn variant="tonal" size="small" class="mt-3" @click="handleRegenerate(d.id)">
                          <v-icon start size="15">mdi-refresh</v-icon>
                          Retry
                        </v-btn>
                      </div>
                      <!-- Edit mode -->
                      <template v-else-if="editingDesignId === d.id">
                        <textarea
                          v-model="editDesign"
                          class="section-editor"
                          placeholder="HTML wireframe content..."
                          @blur="saveDesignById(d.id)"
                        />
                      </template>
                      <!-- Ready with HTML — use blob URL for full interactivity -->
                      <template v-else-if="d.design_html">
                        <iframe
                          :key="d.id + '-' + designPreviewKey"
                          :src="designPreviewUrl(d.id)"
                          class="design-iframe"
                        />
                        <!-- Notes / Figma links -->
                        <div class="design-notes-row">
                          <v-text-field
                            :model-value="d.notes || ''"
                            variant="outlined"
                            density="compact"
                            placeholder="Add notes, Figma link, or design references..."
                            hide-details
                            prepend-inner-icon="mdi-link-variant"
                            class="design-notes-input"
                            @update:model-value="(v: string) => debouncedSaveNotes(d.id, v)"
                          />
                        </div>
                      </template>
                      <!-- Pending (no HTML yet) -->
                      <div v-else class="section-empty">
                        <v-icon icon="mdi-palette-outline" size="40" class="mb-3" />
                        <div>Waiting for generation...</div>
                      </div>
                    </v-tabs-window-item>
                  </v-tabs-window>
                </div>

                <!-- Empty state: generate -->
                <div v-else class="section-empty">
                  <v-icon icon="mdi-palette-outline" size="40" class="mb-3" />
                  <div>No design yet</div>
                  <div class="text-caption text-medium-emphasis mt-1 mb-3">
                    Generate wireframes using your repos' design systems
                  </div>
                  <v-btn variant="tonal" size="small" @click="triggerDesignGeneration">
                    <v-icon start size="15">mdi-creation-outline</v-icon>
                    Generate Wireframes
                  </v-btn>
                </div>
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

              <!-- Test Plan -->
              <v-tabs-window-item value="test-plan">
                <textarea
                  v-if="editingTestPlan"
                  v-model="editTestPlan"
                  class="section-editor"
                  placeholder="Test cases and testing strategy..."
                  @blur="saveTestPlan"
                />
                <div
                  v-else-if="bud.test_plan_md"
                  class="rendered-markdown"
                  v-html="renderMarkdown(bud.test_plan_md)"
                />
                <div v-else class="section-empty">
                  <v-icon icon="mdi-clipboard-check-outline" size="40" class="mb-3" />
                  <div>No test plan yet</div>
                  <v-btn variant="tonal" size="small" class="mt-3" @click="toggleTestPlanEdit">
                    <v-icon start size="15">mdi-pencil-outline</v-icon>
                    Start writing
                  </v-btn>
                </div>
              </v-tabs-window-item>
            </v-tabs-window>
          </div>

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

      <!-- Repo selection dialog for design generation -->
      <v-dialog v-model="showRepoDialog" max-width="480">
        <v-card color="surface" class="pa-6">
          <div class="text-h6 mb-1">Select Repository</div>
          <div class="text-body-2 text-medium-emphasis mb-4">
            Select which repository to generate a design wireframe for.
          </div>
          <div v-if="availableReposLoading" class="d-flex justify-center py-4">
            <v-progress-circular indeterminate size="24" />
          </div>
          <div v-else-if="availableRepos.length > 0" style="max-height: 300px; overflow-y: auto;" class="mx-n2 px-2">
            <v-checkbox
              v-for="repo in availableRepos"
              :key="repo.id"
              v-model="selectedRepoIds"
              :value="repo.id"
              density="compact"
              hide-details
              class="mb-2"
            >
              <template #label>
                <div>
                  <div class="text-body-2 font-weight-medium">{{ repo.name }}</div>
                  <div class="text-caption text-medium-emphasis" style="word-break: break-all;">{{ repo.path }}</div>
                </div>
              </template>
            </v-checkbox>
          </div>
          <div v-else class="text-body-2 text-medium-emphasis py-2">
            No tracked repositories found. Add repositories in Settings.
          </div>
          <v-card-actions class="pa-0 mt-4">
            <v-spacer />
            <v-btn variant="text" @click="showRepoDialog = false">Cancel</v-btn>
            <v-btn color="primary" variant="flat" @click="confirmDesignGeneration">
              Generate
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Reject Tech Arch dialog -->
      <v-dialog v-model="showRejectDialog" max-width="440">
        <v-card color="surface" class="pa-6">
          <div class="text-h6 mb-2">Reject Tech Plan</div>
          <div class="text-body-2 text-medium-emphasis mb-4">
            Provide a reason so the team can revise the plan.
          </div>
          <v-textarea
            v-model="rejectReason"
            variant="outlined"
            label="Reason"
            rows="3"
            counter="5000"
            :rules="[v => !!v?.trim() || 'Reason is required']"
          />
          <v-card-actions class="pa-0">
            <v-spacer />
            <v-btn variant="text" @click="showRejectDialog = false">Cancel</v-btn>
            <v-btn color="error" variant="flat" :disabled="!rejectReason?.trim()" @click="handleRejectTechArch">
              Reject
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Reassignment dialog -->
      <v-dialog v-model="showReassignDialog" max-width="440">
        <v-card color="surface" class="pa-6">
          <div class="text-h6 mb-2">Request Reassignment</div>
          <div class="text-body-2 text-medium-emphasis mb-4">
            Explain why you'd like to hand off this BUD to another developer.
          </div>
          <v-textarea
            v-model="reassignReason"
            variant="outlined"
            label="Reason"
            rows="3"
            counter="5000"
            :rules="[v => !!v?.trim() || 'Reason is required']"
          />
          <v-card-actions class="pa-0">
            <v-spacer />
            <v-btn variant="text" @click="showReassignDialog = false">Cancel</v-btn>
            <v-btn color="warning" variant="flat" :disabled="!reassignReason?.trim()" @click="handleReassignment">
              Request Reassignment
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Repo Confirmation Dialog (for code_review transition) -->
      <v-dialog v-model="showRepoConfirmDialog" max-width="520">
        <v-card>
          <v-card-title>Confirm Repos for Code Review</v-card-title>
          <v-card-text>
            <p class="text-body-2 mb-3">Select which repositories should be included in the code review:</p>
            <v-list density="compact">
              <v-list-item v-for="repo in commitRepos" :key="repo.repoPath">
                <template #prepend>
                  <v-checkbox-btn v-model="repo.checked" density="compact" />
                </template>
                <v-list-item-title class="text-body-2">{{ repo.repoName }}</v-list-item-title>
                <v-list-item-subtitle class="text-caption">{{ repo.commitCount }} commit{{ repo.commitCount !== 1 ? 's' : '' }}</v-list-item-subtitle>
              </v-list-item>
            </v-list>
            <v-alert v-if="commitRepos.length === 0" type="warning" variant="tonal" density="compact" class="mt-2">
              No commits found for this BUD. You can still proceed but the review will have no code changes to analyze.
            </v-alert>
            <v-text-field
              v-if="commitRepos.some(r => !r.checked)"
              v-model="excludeReason"
              label="Reason for excluding repos"
              variant="outlined"
              density="compact"
              class="mt-3"
            />
          </v-card-text>
          <v-card-actions>
            <v-btn variant="text" @click="showRepoConfirmDialog = false">Cancel</v-btn>
            <v-spacer />
            <v-btn color="primary" variant="flat" @click="confirmCodeReviewTransition">
              Start Code Review
            </v-btn>
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
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { useAuthStore } from '@/stores/auth'
import { useMembersStore } from '@/stores/members'
import { useSettingsStore } from '@/stores/settings'
import { useJobSocket } from '@/composables/useJobSocket'
import { useMarkdownSection } from '@/composables/useMarkdownSection'
import { BUD_STATUS_ORDER, BUD_STATUS_LABELS, BUD_STATUS_COLORS, BUD_SECTIONS, VALID_BUD_TABS, TAB_TO_SECTION } from '@/types'
import type { BUDDesign, RepoInfo, BUDSectionKey, TimelineEvent } from '@/types'
import ChatPanel from '@/components/buds/ChatPanel.vue'
import BUDTimeline from '@/components/buds/BUDTimeline.vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

const route = useRoute()
const router = useRouter()
const budStore = useBUDStore()
const authStore = useAuthStore()
const membersStore = useMembersStore()
const settingsStore = useSettingsStore()

const bud = computed(() => budStore.currentBUD)

const activeTab = ref('requirements')
const confirmDelete = ref(false)

// Tech architecture approval / reassignment state
const showRejectDialog = ref(false)
const showReassignDialog = ref(false)
const rejectReason = ref('')
const reassignReason = ref('')
const approvingTechArch = ref(false)

const canApprove = computed(() => {
  const role = authStore.user?.role
  return role === 'tech_lead' || role === 'manager' || role === 'org_owner'
})

const isCurrentAssignee = computed(() =>
  bud.value?.assignee_id != null && authStore.user?.id === bud.value.assignee_id,
)

const awaitingManagerApproval = computed(() => {
  const meta = bud.value?.metadata as Record<string, unknown> | null
  const approval = meta?.tech_arch_approval as Record<string, unknown> | undefined
  return approval?.awaiting_manager === true
})

async function handleApproveTechArch(): Promise<void> {
  if (!bud.value) return
  approvingTechArch.value = true
  try {
    await budStore.approveTechArch(bud.value.id)
  } finally {
    approvingTechArch.value = false
  }
}

async function handleRejectTechArch(): Promise<void> {
  if (!bud.value || !rejectReason.value.trim()) return
  await budStore.rejectTechArch(bud.value.id, rejectReason.value)
  showRejectDialog.value = false
  rejectReason.value = ''
}

async function handleReassignment(): Promise<void> {
  if (!bud.value || !reassignReason.value.trim()) return
  await budStore.requestReassignment(bud.value.id, reassignReason.value)
  showReassignDialog.value = false
  reassignReason.value = ''
}

// Timeline + assignee state
const timelineEvents = ref<TimelineEvent[]>([])
const timelineLoading = ref(false)
const timelineOpen = ref(false)
const assigneeSearch = ref('')

// Title editing
const editingTitle = ref(false)
const editTitle = ref('')

// Markdown section editing via composable (replaces manual toggle/save per section)
const { editing: editingContent, editValue: editContent, toggle: toggleContentEdit, save: saveContent } =
  useMarkdownSection('requirements_md', bud)
const { editing: editingTechSpec, editValue: editTechSpec, toggle: toggleTechSpecEdit, save: saveTechSpec } =
  useMarkdownSection('tech_spec_md', bud)
const { editing: editingTestPlan, editValue: editTestPlan, toggle: toggleTestPlanEdit, save: saveTestPlan } =
  useMarkdownSection('test_plan_md', bud)
const editDesign = ref('')

// Multi-design state
const designs = ref<BUDDesign[]>([])
const activeDesignTab = ref<string>('')
const editingDesignId = ref<string | null>(null)
const showRepoDialog = ref(false)
const availableRepos = ref<RepoInfo[]>([])
const availableReposLoading = ref(false)
const selectedRepoIds = ref<string[]>([])
const designJobProgress = reactive(new Map<string, string>())
const designPreviewKey = ref(0) // bump to force iframe reload
let notesSaveTimer: ReturnType<typeof setTimeout> | null = null

const activeDesignObj = computed(() =>
  designs.value.find(d => d.id === activeDesignTab.value) || null,
)

// Blob URLs for iframe rendering (no auth required)
const designBlobUrls = reactive(new Map<string, string>())

function updateBlobUrls(): void {
  // Revoke old URLs
  for (const url of designBlobUrls.values()) {
    URL.revokeObjectURL(url)
  }
  designBlobUrls.clear()
  for (const d of designs.value) {
    if (d.design_html) {
      const blob = new Blob([d.design_html], { type: 'text/html' })
      designBlobUrls.set(d.id, URL.createObjectURL(blob))
    }
  }
}

function designPreviewUrl(designId: string): string {
  return designBlobUrls.get(designId) || ''
}

function openDesignInTab(designId: string): void {
  const d = designs.value.find(dd => dd.id === designId)
  if (!d?.design_html) return
  const blob = new Blob([d.design_html], { type: 'text/html' })
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank')
  // Revoke after 60s — browser keeps the tab content after opening
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}

function refreshDesignPreview(): void {
  updateBlobUrls()
  designPreviewKey.value++
}

function debouncedSaveNotes(designId: string, value: string): void {
  if (notesSaveTimer) clearTimeout(notesSaveTimer)
  notesSaveTimer = setTimeout(async () => {
    if (!bud.value) return
    await budStore.updateDesignNotes(bud.value.id, designId, value)
    const idx = designs.value.findIndex(d => d.id === designId)
    if (idx !== -1) designs.value[idx] = { ...designs.value[idx], notes: value }
  }, 800)
}

// PRD generation tracking
const prdGenerating = ref(false)
const prdStatusMessage = ref('')

// Tech arch generation tracking
const techArchGenerating = ref(false)
const techArchStatusMessage = ref('')

// Code review tracking
const codeReviewGenerating = ref(false)
const codeReviewStatusMessage = ref('')
const showRepoConfirmDialog = ref(false)
const commitRepos = ref<{ repoPath: string; repoName: string; commitCount: number; checked: boolean }[]>([])
const excludeReason = ref('')

interface CodeReviewComment {
  repo: string
  file: string
  line: number
  severity: 'error' | 'warning' | 'suggestion'
  comment: string
  deviates_from_spec: boolean
  status?: 'pending' | 'accepted' | 'skipped'
  skip_reason?: string
}

const codeReviewComments = computed<CodeReviewComment[]>(() => {
  const meta = bud.value?.metadata as Record<string, unknown> | null
  return (meta?.code_review_comments as CodeReviewComment[] | undefined) ?? []
})

const automationTestPlan = computed(() => {
  const meta = bud.value?.metadata as Record<string, unknown> | null
  return (meta?.automation_test_plan_md as string | undefined) ?? ''
})

const manualTestPlan = computed(() => {
  const meta = bud.value?.metadata as Record<string, unknown> | null
  return (meta?.manual_test_plan_md as string | undefined) ?? ''
})

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
  if (activeTab.value === 'design') return editingDesignId.value !== null
  return editingContent.value
})

// ── Markdown rendering ────────────────────────────────
function renderMarkdown(md: string | null): string {
  if (!md) return ''
  const raw = marked.parse(md, { async: false }) as string
  return DOMPurify.sanitize(raw)
}

onMounted(async () => {
  // Apply deep-link tab BEFORE data fetches so loadChatHistory()
  // targets the correct section and avoids a visual flash + double load.
  const tabParam = route.query.tab as string | undefined
  if (tabParam && VALID_BUD_TABS.has(tabParam)) {
    activeTab.value = tabParam
  }

  const id = route.params.id as string
  await budStore.fetchBUD(id)
  await loadDesigns()
  await loadChatHistory()
  trackPrdJobIfActive()
  trackTechArchJobIfActive()
  trackCodeReviewJobIfActive()
  membersStore.fetchMembers()
  loadTimeline()
})

onBeforeUnmount(() => {
  // Clean up blob URLs
  for (const url of designBlobUrls.values()) {
    URL.revokeObjectURL(url)
  }
})

// Resume tech arch job tracking when metadata changes (e.g. after status update re-fetch)
watch(() => bud.value?.metadata?.tech_arch_job_id, (newJobId) => {
  if (newJobId && !techArchGenerating.value) {
    trackTechArchJobIfActive()
  }
})

// Resume code review job tracking when metadata changes
watch(() => (bud.value?.metadata as Record<string, unknown> | null)?.code_review_job_id, (newJobId) => {
  if (newJobId && !codeReviewGenerating.value) {
    trackCodeReviewJobIfActive()
  }
})

// Load chat history when switching tabs or design sub-tabs
watch(activeTab, () => {
  currentSessionId.value = undefined
  loadChatHistory()
})
watch(activeDesignTab, () => {
  if (activeTab.value === 'design') loadChatHistory()
})

async function loadChatHistory(): Promise<void> {
  if (!bud.value) return
  const section = currentSection.value
  const designId = section === 'design' && activeDesignTab.value
    ? activeDesignTab.value
    : undefined
  const history = await budStore.fetchChatHistory(bud.value.id, section, designId, currentSessionId.value)
  chatMessages.value = history.map(m => ({ role: m.role, text: m.message, userName: m.user_name }))
}

function startNewSession(): void {
  currentSessionId.value = crypto.randomUUID()
  chatMessages.value = []
}

function startEditTitle(): void {
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
  }
  editingTitle.value = false
}

async function updateStatus(newStatus: string): Promise<void> {
  if (!bud.value) return

  // Intercept code_review transition to show repo confirmation
  if (newStatus === 'code_review') {
    await showCodeReviewConfirmation()
    return
  }

  await budStore.updateBUD(bud.value.id, { status: newStatus } as never)

  // If entering design phase, trigger design generation flow
  if (budStore.designAvailable) {
    budStore.designAvailable = false
    await triggerDesignGeneration()
  }

  await loadTimeline()
}

async function showCodeReviewConfirmation(): Promise<void> {
  if (!bud.value) return
  try {
    const resp = await fetch(`/api/v1/buds/${bud.value.id}/commits/repos`, {
      headers: { 'Authorization': `Bearer ${useAuthStore().token}` },
    })
    if (resp.ok) {
      const repos = await resp.json()
      commitRepos.value = repos.map((r: { repo_path: string; repo_name: string; commit_count: number }) => ({
        repoPath: r.repo_path,
        repoName: r.repo_name,
        commitCount: r.commit_count,
        checked: true,
      }))
    } else {
      commitRepos.value = []
    }
  } catch {
    commitRepos.value = []
  }
  showRepoConfirmDialog.value = true
}

async function confirmCodeReviewTransition(): Promise<void> {
  if (!bud.value) return
  showRepoConfirmDialog.value = false

  const confirmedRepos = commitRepos.value
    .filter(r => r.checked)
    .map(r => ({
      repo_path: r.repoPath,
      repo_name: r.repoName,
    }))
  const excludedRepos = commitRepos.value
    .filter(r => !r.checked)
    .map(r => ({
      repo_path: r.repoPath,
      repo_name: r.repoName,
      reason: excludeReason.value || 'Excluded by user',
    }))

  // Set confirmed repos in metadata before transition
  const meta = { ...(bud.value.metadata || {}), confirmed_repos: confirmedRepos, excluded_repos: excludedRepos }
  await budStore.updateBUD(bud.value.id, { metadata: meta, status: 'code_review' } as never)

  // Track the code review job
  const refreshed = budStore.currentBUD
  const crJobId = (refreshed?.metadata as Record<string, unknown> | null)?.code_review_job_id as string | undefined
  if (crJobId) {
    trackCodeReviewJob(crJobId)
  }

  await loadTimeline()
}

function trackCodeReviewJob(jobId: string): void {
  codeReviewGenerating.value = true
  codeReviewStatusMessage.value = 'Starting code review...'
  startTracking(jobId, {
    onProgress(s) {
      codeReviewStatusMessage.value = s.statusMessage || 'Reviewing code...'
    },
    async onComplete() {
      codeReviewGenerating.value = false
      codeReviewStatusMessage.value = ''
      await budStore.fetchBUD(bud.value!.id)
    },
    onError(err) {
      codeReviewGenerating.value = false
      codeReviewStatusMessage.value = `Failed: ${err}`
    },
  })
}

async function handleReviewComment(idx: number, action: 'accepted' | 'skipped', reason?: string): Promise<void> {
  if (!bud.value) return
  const meta = { ...(bud.value.metadata || {}) } as Record<string, unknown>
  const comments = [...(meta.code_review_comments as CodeReviewComment[] || [])]
  if (comments[idx]) {
    comments[idx] = { ...comments[idx], status: action }
    if (reason) comments[idx].skip_reason = reason
    meta.code_review_comments = comments
    await budStore.updateBUD(bud.value.id, { metadata: meta } as never)
  }
}

// ── Multi-design functions ────────────────────────────

async function loadDesigns(): Promise<void> {
  if (!bud.value) return
  designs.value = await budStore.fetchDesigns(bud.value.id)
  updateBlobUrls()
  designPreviewKey.value++ // Force iframe reload with new blob URLs
  if (designs.value.length > 0 && !activeDesignTab.value) {
    activeDesignTab.value = designs.value[0].id
  }
  // Resume tracking for any in-progress designs
  for (const d of designs.value) {
    if (d.status === 'generating' && d.job_id) {
      trackDesignJob(d.id, d.job_id)
    }
  }
}

async function triggerDesignGeneration(): Promise<void> {
  if (!bud.value) return
  availableReposLoading.value = true
  await settingsStore.fetchRepos()
  const activeRepos = settingsStore.repos.filter(r => r.status === 'active')
  availableRepos.value = activeRepos
  availableReposLoading.value = false

  if (activeRepos.length === 0) {
    await startDesignJobs([])
  } else if (activeRepos.length === 1) {
    await startDesignJobs([activeRepos[0].id])
  } else {
    selectedRepoIds.value = []
    showRepoDialog.value = true
  }
}

async function confirmDesignGeneration(): Promise<void> {
  showRepoDialog.value = false
  await startDesignJobs(selectedRepoIds.value)
}

async function startDesignJobs(repoIds: string[]): Promise<void> {
  if (!bud.value) return
  const jobs = await budStore.generateDesigns(bud.value.id, repoIds)

  // Reload designs to get the created rows
  await loadDesigns()
  activeTab.value = 'design'

  // Track each job
  for (const job of jobs) {
    trackDesignJob(job.designId, job.jobId)
  }
}

function trackDesignJob(designId: string, jobId: string): void {
  startTracking(jobId, {
    onProgress(s) {
      designJobProgress.set(designId, s.statusMessage || 'Generating wireframe...')
    },
    async onComplete(data) {
      designJobProgress.delete(designId)
      // Re-fetch designs from DB to get persisted HTML (too large for WebSocket)
      await loadDesigns()
      const result = data as { reply?: string } | null
      if (result?.reply) {
        chatMessages.value.push({ role: 'ai', text: result.reply })
      }
    },
    async onError(err) {
      designJobProgress.delete(designId)
      const idx = designs.value.findIndex(d => d.id === designId)
      if (idx !== -1) {
        designs.value[idx] = { ...designs.value[idx], status: 'failed' }
      }
      chatMessages.value.push({ role: 'ai', text: `Design generation failed: ${err}` })
      // Re-fetch from DB to sync sibling designs that may have also failed
      // (their WS subscriptions can be lost during rapid re-renders)
      await loadDesigns()
    },
  })
}

function trackPrdJobIfActive(): void {
  const jobId = bud.value?.metadata?.prd_job_id as string | undefined
  if (!jobId) return
  prdGenerating.value = true
  startTracking(jobId, {
    onProgress(s) {
      prdStatusMessage.value = s.statusMessage || 'PRD agent is enriching requirements...'
    },
    async onComplete() {
      prdGenerating.value = false
      prdStatusMessage.value = ''
      // Refresh BUD to show the enriched content
      if (bud.value) await budStore.fetchBUD(bud.value.id)
    },
    onError() {
      prdGenerating.value = false
      prdStatusMessage.value = ''
    },
  })
}

function trackTechArchJobIfActive(): void {
  const jobId = bud.value?.metadata?.tech_arch_job_id as string | undefined
  if (!jobId) return
  techArchGenerating.value = true
  startTracking(jobId, {
    onProgress(s) {
      techArchStatusMessage.value = s.statusMessage || 'Generating tech architecture...'
    },
    async onComplete() {
      techArchGenerating.value = false
      techArchStatusMessage.value = ''
      if (bud.value) await budStore.fetchBUD(bud.value.id)
    },
    onError() {
      techArchGenerating.value = false
      techArchStatusMessage.value = ''
    },
  })
}

function trackCodeReviewJobIfActive(): void {
  const meta = bud.value?.metadata as Record<string, unknown> | null
  const jobId = meta?.code_review_job_id as string | undefined
  if (!jobId) return
  trackCodeReviewJob(jobId)
}

async function handleRegenerate(designId: string): Promise<void> {
  if (!bud.value) return
  const result = await budStore.regenerateDesign(bud.value.id, designId)
  if (result) {
    const idx = designs.value.findIndex(d => d.id === designId)
    if (idx !== -1) {
      designs.value[idx] = { ...designs.value[idx], status: 'generating', job_id: result.jobId }
    }
    trackDesignJob(designId, result.jobId)
  }
}

async function saveDesignById(designId: string): Promise<void> {
  if (!bud.value) return
  const d = designs.value.find(d => d.id === designId)
  if (d && editDesign.value !== (d.design_html || '')) {
    await budStore.updateDesignHtml(bud.value.id, designId, editDesign.value)
    const idx = designs.value.findIndex(dd => dd.id === designId)
    if (idx !== -1) designs.value[idx] = { ...designs.value[idx], design_html: editDesign.value }
  }
  editingDesignId.value = null
}

// Unified toggle for whichever tab is active
function toggleEdit(): void {
  if (activeTab.value === 'tech-spec') toggleTechSpecEdit()
  else if (activeTab.value === 'test-plan') toggleTestPlanEdit()
  else if (activeTab.value === 'design') toggleDesignEdit()
  else toggleContentEdit()
}

function toggleDesignEdit(): void {
  // Multi-design mode: edit active tab's design
  if (designs.value.length > 0 && activeDesignTab.value) {
    if (editingDesignId.value === activeDesignTab.value) {
      saveDesignById(activeDesignTab.value)
    } else {
      const d = designs.value.find(d => d.id === activeDesignTab.value)
      editDesign.value = d?.design_html || ''
      editingDesignId.value = activeDesignTab.value
    }
    return
  }
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

  const chatDesignId = currentSection.value === 'design' && activeDesignTab.value
    ? activeDesignTab.value
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
      const { reply, updated_content } = data as { reply: string; updated_content: string | null }
      chatMessages.value.push({ role: 'ai', text: reply })
      if (updated_content !== null) {
        if (budStore.currentBUD) {
          (budStore.currentBUD as Record<string, unknown>)[currentSection.value] = updated_content
        }
        if (currentSection.value === 'requirements_md' && editingContent.value) {
          editContent.value = updated_content
        } else if (currentSection.value === 'tech_spec_md' && editingTechSpec.value) {
          editTechSpec.value = updated_content
        } else if (currentSection.value === 'test_plan_md' && editingTestPlan.value) {
          editTestPlan.value = updated_content
        } else if (currentSection.value === 'design') {
          if (bud.value) await loadDesigns()
          refreshDesignPreview()
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
    const html = activeDesignObj.value?.design_html
    if (!html) return
    const repoName = activeDesignObj.value?.repo_name || 'default'
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

/* ── Multi-design sub-tabs ─────────────────────── */
.design-multi-panel {
  display: flex;
  flex-direction: column;
}

.design-sub-tabs-row {
  display: flex;
  align-items: center;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  padding: 0 8px;
}

.design-sub-tabs {
  flex: 1;
}

/* ── Design notes ──────────────────────────────── */
.design-notes-row {
  padding: 8px 12px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  background: rgba(var(--v-theme-on-surface), 0.02);
}

.design-notes-input {
  font-size: 13px;
}

/* ── Design iframe ─────────────────────────────── */
.design-iframe {
  width: 100%;
  min-height: 600px;
  border: none;
  background: #0f1117;
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
</style>
