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

<!-- One BUD: header, stage stepper, agent banners, the section tabs with
     details and activity beside them, and the AI chat panel on the right. -->
<template>
  <div class="bud-detail-layout">
    <div class="bud-main">
      <!-- A skeleton in the page's shape reads as "forming", not as a hang. -->
      <div v-if="budStore.loading" class="bud-page">
        <v-skeleton-loader type="heading" />
        <v-skeleton-loader type="text" width="35%" />
        <v-skeleton-loader type="button@5" />
        <v-skeleton-loader type="paragraph@4" />
      </div>

      <!-- Only a failed load replaces the page. A failed action (a refused
           status change, say) is reported above the content instead, so
           the user keeps their place. -->
      <div v-else-if="budStore.error && !bud" class="bud-page">
        <AppCallout variant="error" title="This BUD didn't load">{{ budStore.error }}</AppCallout>
      </div>

      <div v-else-if="bud" class="bud-page">
        <AppCallout v-if="budStore.error" variant="error">
          {{ budStore.error }}
          <template #actions>
            <v-btn icon="mdi-close" variant="text" size="small" aria-label="Dismiss error" @click="budStore.error = ''" />
          </template>
        </AppCallout>

        <BUDHeader
          :bud="bud"
          :status-items="statusItems"
          :next-status="nextStatus"
          :is-closed="isClosed"
          :agent-locked="agentLocked"
          :chat-open="chatOpen"
          :chatable="currentSectionChatable"
          :can-edit-priority="canEditBud"
          :can-edit-buds="canEditBud"
          @update:chat-open="chatOpen = $event"
          @change-assignee="changeAssignee"
          @change-priority="changePriority"
          @update-status="updateStatus"
          @restore="restoreDialog?.open(bud)"
          @delete="confirmDelete = true"
          @save-title="saveTitle"
          @open-skill-settings="skillSettingsOpen = true"
          @open-history="openHistory"
        />

        <BUDStageStepper :phase-order="phaseOrder" :status="bud.status" />

        <BUDExternalLlmCallout v-if="isExternalLlmMode" @open-skill-settings="skillSettingsOpen = true" />
        <BUDWorkflowActions
          ref="workflowRef"
          :bud="bud"
          :can-approve="canApprove"
          :is-current-assignee="isCurrentAssignee"
          @reload-timeline="loadTimeline(); reloadEstimates()"
        />
        <BUDAgentBanners
          :generating-designs="generatingDesigns"
          :agent-running="agentRunning"
          :agent-name="workflowRef?.agentName"
          :agent-status-message="workflowRef?.agentStatusMessage"
          :task="bud.active_agent_task"
          :cancelling-design-id="cancellingDesignId"
          :cancelling-agent="cancellingAgent"
          @cancel-design="cancelDesign"
          @cancel-agent="cancelRunningAgent"
          @retry="budStore.retryAgentTask(bud.id, $event)"
        />

        <BUDDetailTabBar v-model="activeTab" :tabs="tabs">
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
            @import-section="importSection"
          />
        </BUDDetailTabBar>

        <div class="bud-page__grid">
          <div class="bud-page__main">
            <BUDDetailTabPanels
              ref="panelsRef"
              v-model:tab="activeTab"
              v-model:requirements-draft="editContent"
              v-model:tech-spec-draft="editTechSpec"
              :bud="bud"
              :editing-requirements="editingContent"
              :editing-tech-spec="editingTechSpec"
              :agent-locked="agentLocked"
              :uat-enabled="uatStageEnabled"
              :is-closed="isClosed"
              :has-learning="hasLearning"
              :timeline-events="timelineEvents"
              :learning-refresh-key="learningRefreshKey"
              @save-requirements="saveContent"
              @edit-requirements="toggleContentEdit"
              @enrich="enrichWithAI"
              @save-tech-spec="saveTechSpec"
              @edit-tech-spec="toggleTechSpecEdit"
              @open-tech-spec-chat="openTechSpecChat"
              @chat-message="chatMessages.push($event)"
              @design-tab-change="loadChatHistory"
              @download-tech-spec="downloadSection('tech_spec_md')"
              @refresh="refreshBudAndTimeline"
              @timeline-changed="loadTimeline"
            />
            <!-- No forecast once a BUD has closed or been discarded. -->
            <BUDEstimationSection v-if="!isClosed" ref="estimationRef" :bud-id="bud.id" :current-phase="bud.status" />
            <BUDBugsPanel :bud-id="bud.id" :bud-status="bud.status" />
          </div>
          <aside class="bud-page__aside" aria-label="BUD details">
            <BUDDetailsPanel :bud="bud" @change-assignee="changeAssignee" />
            <BUDActivitySection :events="timelineEvents" :loading="timelineLoading" />
          </aside>
        </div>
      </div>

      <!-- Reloads the timeline so the restore shows up without a refresh. -->
      <BUDRestoreDialog ref="restoreDialog" @restored="loadTimeline" />
      <!-- Status guard dialogs and snackbars; Vuetify teleports them. -->
      <BUDStatusDialogs :controller="statusController" />
      <template v-if="bud">
        <!-- Refetch on save so the banner and the next stage change see the
             new auto_generate_phases. -->
        <BUDSkillSettingsDialog
          v-model="skillSettingsOpen"
          :bud-id="bud.id"
          :auto-generate-phases="bud.auto_generate_phases ?? null"
          @saved="refreshAfterSettingsSave"
        />
        <BUDSectionDiffDrawer
          v-model="sectionDiffOpen"
          :bud-id="bud.id"
          :bud-status="bud.status"
          :section="sectionDiffSection"
          @reverted="refreshBudAndTimeline"
        />
        <BUDDeleteDialog v-model="confirmDelete" :bud="bud" @confirm="deleteBud" />
      </template>
    </div>

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
        :selected-design-id="designPanel?.activeDesignTab ?? undefined"
        :needs-design-generation="needsDesignGeneration"
        @close="chatOpen = false"
        @send="handleChatSend"
        @cancel="handleChatCancel"
        @new-session="startNewSession"
        @retry="manualRetry"
        @select-design="designPanel?.setActiveDesignTab($event)"
        @open-generate-designs="openGenerateDesigns"
        @open-autogen-settings="skillSettingsOpen = true"
      />
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import BUDActivitySection from '@/components/buds/BUDActivitySection.vue'
import BUDBugsPanel from '@/components/buds/BUDBugsPanel.vue'
import BUDEstimationSection from '@/components/buds/BUDEstimationSection.vue'
import BUDHeader from '@/components/buds/BUDHeader.vue'
import BUDRestoreDialog from '@/components/buds/BUDRestoreDialog.vue'
import BUDSectionDiffDrawer from '@/components/buds/BUDSectionDiffDrawer.vue'
import BUDSectionToolbar from '@/components/buds/BUDSectionToolbar.vue'
import BUDSkillSettingsDialog from '@/components/buds/BUDSkillSettingsDialog.vue'
import BUDStatusDialogs from '@/components/buds/BUDStatusDialogs.vue'
import BUDWorkflowActions from '@/components/buds/BUDWorkflowActions.vue'
import ChatPanel from '@/components/buds/ChatPanel.vue'
import BUDAgentBanners from '@/components/buds/detail/BUDAgentBanners.vue'
import BUDDeleteDialog from '@/components/buds/detail/BUDDeleteDialog.vue'
import BUDDetailsPanel from '@/components/buds/detail/BUDDetailsPanel.vue'
import BUDDetailTabBar from '@/components/buds/detail/BUDDetailTabBar.vue'
import BUDDetailTabPanels from '@/components/buds/detail/BUDDetailTabPanels.vue'
import BUDExternalLlmCallout from '@/components/buds/detail/BUDExternalLlmCallout.vue'
import BUDStageStepper from '@/components/buds/detail/BUDStageStepper.vue'
import { useBudActivityChannel } from '@/composables/useBudActivityChannel'
import { useBudAgentTracking } from '@/composables/useBudAgentTracking'
import { useBudChat } from '@/composables/useBudChat'
import { useBudDetailActions } from '@/composables/useBudDetailActions'
import { useBudDetailTabs } from '@/composables/useBudDetailTabs'
import { useBudHistoryDrawer } from '@/composables/useBudHistoryDrawer'
import { useBudSectionFiles } from '@/composables/useBudSectionFiles'
import { useBudStatusTransitions } from '@/composables/useBudStatusTransitions'
import { useBudTimeline } from '@/composables/useBudTimeline'
import { useMarkdownSection } from '@/composables/useMarkdownSection'
import { usePermissions } from '@/composables/usePermissions'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import { useAuthStore } from '@/stores/auth'
import { useBUDStore } from '@/stores/bud'
import { useBudLinkedFeaturesStore } from '@/stores/budLinkedFeatures'
import { useMembersStore } from '@/stores/members'
import { useSettingsStore } from '@/stores/settings'
import { BUD_STATUS_LABELS, VALID_BUD_TABS } from '@/types'
import { STATUS_TAB_MAP, nextStage } from '@/utils/budDetail'
import '@/components/buds/agent-banner.css'

const route = useRoute()
const budStore = useBUDStore()
const authStore = useAuthStore()
const membersStore = useMembersStore()
const settingsStore = useSettingsStore()
const budLinkedFeaturesStore = useBudLinkedFeaturesStore()
const { hasPermission } = usePermissions()
const { phaseOrder } = usePhaseOrder()

// The store keeps currentBUD to the BUD this page navigated to: only a
// foreground fetchBUD sets it, background refreshes no-op on a mismatch.
const bud = computed(() => budStore.currentBUD)
// Mirrors the PATCH endpoint's gate for priority, header stage moves and restore.
const canEditBud = computed(() => hasPermission('buds:edit'))
const canApprove = computed(() => ['tech_lead', 'manager', 'org_owner'].includes(authStore.user?.role ?? ''))
const isCurrentAssignee = computed(() => bud.value?.assignee_id != null && authStore.user?.id === bud.value.assignee_id)
// Every stage agent off (or none set, the default for new BUDs): the
// person drives the BUD from their own AI. Guarded on bud so the callout
// doesn't flash during the first fetch.
const isExternalLlmMode = computed(() => {
  if (!bud.value) return false
  const phases = bud.value.auto_generate_phases
  return !phases || !Object.values(phases).some(Boolean)
})

const {
  activeTab, tabs, uatStageEnabled, isClosed, hasLearning, isReadOnlyTab, currentSection, currentSectionLabel,
  currentSectionEditable, currentSectionChatable, needsDesignGeneration, editLockTooltip,
} = useBudDetailTabs(bud)
const { sectionDiffOpen, sectionDiffSection, openHistory } = useBudHistoryDrawer(activeTab)
const { timelineEvents, timelineLoading, loadTimeline } = useBudTimeline(bud)
const confirmDelete = ref(false)
const skillSettingsOpen = ref(false)
const learningRefreshKey = ref(0)

const workflowRef = ref<InstanceType<typeof BUDWorkflowActions> | null>(null)
const panelsRef = ref<InstanceType<typeof BUDDetailTabPanels> | null>(null)
const designPanel = computed(() => panelsRef.value?.designPanel ?? null)
const estimationRef = ref<InstanceType<typeof BUDEstimationSection> | null>(null)
const reloadEstimates = (): void => void estimationRef.value?.loadEstimates()

const { agentLocked, agentRunning, generatingDesigns } = useBudAgentTracking(bud, workflowRef)
const { downloadSection, importSection } = useBudSectionFiles(bud, () => designPanel.value?.activeDesignObj)

// Stage changes with their guards (open PRs, pending test cases, manual
// merge override), dialogs and agent cancels. BUDStatusDialogs renders
// the controller's dialogs.
const statusController = useBudStatusTransitions({
  getBud: () => bud.value,
  setActiveTab: (tab) => { activeTab.value = tab },
  getStatusTabMap: () => STATUS_TAB_MAP,
  triggerDesignGeneration: () => designPanel.value?.triggerDesignGeneration(),
  reloadTimeline: () => loadTimeline(),
})
const { updateStatus, cancelRunningAgent, cancellingAgent, cancelDesign, cancellingDesignId } = statusController

// The org's stage list (UAT may be off), for the stage menu and the header's next-stage button.
const statusItems = computed(() => phaseOrder.value.map(s => ({ title: BUD_STATUS_LABELS[s], value: s })))
const nextStatus = computed(() => (bud.value ? nextStage(phaseOrder.value, bud.value.status) : null))

const { editing: editingContent, editValue: editContent, toggle: toggleContentEdit, save: saveContent } =
  useMarkdownSection('requirements_md', bud)
const { editing: editingTechSpec, editValue: editTechSpec, toggle: toggleTechSpecEdit, save: saveTechSpec } =
  useMarkdownSection('tech_spec_md', bud)

const {
  chatOpen, chatLoading, chatMessages, chatStatusMessage, currentSessionId,
  stageGateMessage, chatInProgressBanner, retryPrompt,
  loadChatHistory, startNewSession, handleChatSend, handleChatCancel, manualRetry, enrichWithAI,
} = useBudChat({
  getBud: () => bud.value,
  getCurrentSection: () => currentSection.value,
  getDesignTabId: () => designPanel.value?.activeDesignTab,
  setActiveTab: (tab) => { activeTab.value = tab },
  syncEditor: (section, content) => {
    if (section === 'requirements_md' && editingContent.value) editContent.value = content
    else if (section === 'tech_spec_md' && editingTechSpec.value) editTechSpec.value = content
  },
  onDesignContentUpdated: async () => {
    if (bud.value) await designPanel.value?.loadDesigns()
    designPanel.value?.refreshDesignPreview()
  },
})

// The chat's design picker, only on the Design section; ChatPanel shows it from two designs up.
const chatDesignOptions = computed(() =>
  currentSection.value === 'design'
    ? (bud.value?.designs ?? []).map(d => ({ id: d.id, repoName: d.repo_name }))
    : [],
)

const isEditing = computed(() => {
  if (activeTab.value === 'tech-spec') return editingTechSpec.value
  if (activeTab.value === 'design') return designPanel.value?.editingDesignId !== null
  return editingContent.value
})

// Honours the same stage rule as the toolbar's Edit button.
function toggleEdit(): void {
  if (!currentSectionEditable.value) return
  if (activeTab.value === 'tech-spec') toggleTechSpecEdit()
  else if (activeTab.value === 'design') designPanel.value?.toggleDesignEdit()
  else toggleContentEdit()
}

const channel = useBudActivityChannel({
  refresh: (id) => {
    // The user may have moved to another BUD; the guarded refresh no-ops then.
    void budStore.refreshBUDIfCurrent(id)
    void loadTimeline()
    reloadEstimates()
  },
  onLearningRecorded: () => { learningRefreshKey.value += 1 },
})

// Sets the page up for one BUD. Runs on first mount and on every move
// between BUDs, since the router reuses this component for /buds/A → /buds/B.
async function loadBud(id: string): Promise<void> {
  channel.disconnect()
  startNewSession()
  const tabParam = route.query.tab as string | undefined
  if (tabParam && VALID_BUD_TABS.has(tabParam)) activeTab.value = tabParam
  await budStore.fetchBUD(id)
  if (!tabParam && bud.value) activeTab.value = STATUS_TAB_MAP[bud.value.status] ?? activeTab.value
  await loadChatHistory()
  membersStore.fetchMembers()
  void loadTimeline()
  // UAT visibility and the release tabs' branch links read these.
  if (!settingsStore.connectionsLoaded) settingsStore.fetchConnections()
  if (settingsStore.repos.length === 0) settingsStore.fetchRepos()
  channel.connect(id)
}
watch(() => route.params.id as string, (id) => { if (id) void loadBud(id) }, { immediate: true })

// Close the chat when its section stops being chattable at this stage.
watch(currentSectionChatable, (chatable) => {
  if (!chatable && chatOpen.value) chatOpen.value = false
})
// An agent starting from elsewhere closes the chat (not one the chat
// itself started). Any agent finishing reloads the timeline, estimates
// and linked features, which the PM agent rewrites on every run.
watch(agentLocked, (locked, wasLocked) => {
  if (locked && !chatLoading.value && chatOpen.value) chatOpen.value = false
  if (!locked && wasLocked) {
    void loadTimeline()
    reloadEstimates()
    if (bud.value) void budLinkedFeaturesStore.fetch(bud.value.id)
  }
})
watch(activeTab, () => {
  currentSessionId.value = undefined
  void loadChatHistory()
})

const restoreDialog = ref<InstanceType<typeof BUDRestoreDialog> | null>(null)
const {
  refreshBudAndTimeline, refreshAfterSettingsSave, saveTitle, changeAssignee, changePriority, deleteBud,
} = useBudDetailActions(bud, loadTimeline)

// Tech spec's empty state: open the chat on Tech spec so the AI drafts it.
function openTechSpecChat(): void {
  activeTab.value = 'tech-spec'
  chatOpen.value = true
}

// From the chat's "Generate a design first": show Design, then start generating.
function openGenerateDesigns(): void {
  activeTab.value = 'design'
  void designPanel.value?.triggerDesignGeneration()
}
</script>

<style scoped>
.bud-detail-layout {
  display: flex;
  height: 100%;
  overflow: hidden;
}
.bud-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  background: rgb(var(--v-theme-background));
}
.bud-page {
  container: bud-page / inline-size;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 22px 36px 40px;
}
.bud-page__grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 20px;
  align-items: start;
}
.bud-page__main,
.bud-page__aside {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
@container bud-page (max-width: 1080px) {
  .bud-page__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 600px) {
  .bud-page {
    padding: 20px 16px 32px;
  }
}
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: all var(--dur-mid) ease;
}
.slide-panel-enter-from,
.slide-panel-leave-to {
  width: 0;
  min-width: 0;
  opacity: 0;
}
</style>
