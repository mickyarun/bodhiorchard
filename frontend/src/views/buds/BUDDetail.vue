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
      <!-- Only a failed load replaces the page; a failed action is reported
           above the content so the user keeps their place. -->
      <div v-if="budStore.loading || (budStore.error && !bud)" class="bud-page">
        <BUDDetailLoadState :loading="budStore.loading" :error="budStore.error" @retry="reload" />
      </div>
      <div v-else-if="bud" class="bud-page">
        <AppCallout v-if="budStore.error" variant="error">
          {{ budStore.error }}
          <template #actions>
            <v-btn icon="mdi-close" variant="text" size="small" aria-label="Dismiss error" @click="budStore.error = ''" />
          </template>
        </AppCallout>

        <BUDHeader
          v-model:chat-open="chatOpen"
          :bud="bud" :status-items="statusItems" :next-status="nextStatus" :can-move-to="canMoveTo"
          :changing-status="changingStatus" :is-closed="isClosed" :agent-locked="agentLocked"
          :chatable="currentSectionChatable" :can-edit-priority="canEditBud" :can-edit-buds="canEditBud"
          :can-delete="hasPermission('backlog:delete')"
          @change-assignee="changeAssignee" @change-priority="changePriority" @update-status="updateStatus"
          @restore="dialogs?.openRestore(bud)" @delete="confirmDelete = true" @save-title="saveTitle"
          @open-skill-settings="skillSettingsOpen = true" @open-history="openHistory"
        />

        <BUDStageStepper :phase-order="phaseOrder" :status="bud.status" />

        <BUDExternalLlmCallout v-if="isExternalLlmMode && !isClosed" @open-skill-settings="skillSettingsOpen = true" />
        <BUDWorkflowActions
          ref="workflowRef" :bud="bud" :can-approve="canApprove" :is-current-assignee="isCurrentAssignee"
          @reload-timeline="loadTimeline(); reloadEstimates()"
        />
        <BUDAgentBanners
          :generating-designs="generatingDesigns" :agent-running="agentRunning" :task="bud.active_agent_task"
          :agent-name="workflowRef?.agentName" :agent-status-message="workflowRef?.agentStatusMessage"
          :cancelling-design-id="cancellingDesignId" :cancelling-agent="cancellingAgent"
          @cancel-design="cancelDesign" @cancel-agent="cancelRunningAgent"
          @retry="budStore.retryAgentTask(bud.id, $event)"
        />

        <BUDDetailTabBar v-model="activeTab" :tabs="tabs">
          <BUDSectionToolbar
            v-if="!isReadOnlyTab"
            :is-editing="isEditing" :agent-locked="agentLocked" :active-tab="activeTab"
            :current-section="currentSection" :editable="currentSectionEditable" :edit-lock-tooltip="editLockTooltip"
            @toggle-edit="toggleEdit" @export-section="downloadSection" @import-section="importSection"
          />
        </BUDDetailTabBar>

        <div class="bud-page__grid">
          <div class="bud-page__main">
            <BUDDetailTabPanels
              ref="panelsRef"
              v-model:tab="activeTab"
              :bud="bud" :requirements="requirements" :tech-spec="techSpec" :agent-locked="agentLocked"
              :uat-enabled="uatStageEnabled" :is-closed="isClosed" :has-learning="hasLearning"
              :timeline-events="timelineEvents" :learning-refresh-key="learningRefreshKey"
              @enrich="enrichWithAI" @open-tech-spec-chat="openTechSpecChat" @chat-message="chatMessages.push($event)"
              @design-tab-change="loadChatHistory" @download-tech-spec="downloadSection('tech_spec_md')"
              @refresh="refreshBudAndTimeline" @timeline-changed="loadTimeline"
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

      <BUDDetailDialogs
        ref="dialogs"
        v-model:skill-settings-open="skillSettingsOpen" v-model:history-open="sectionDiffOpen"
        v-model:delete-open="confirmDelete"
        :bud="bud" :controller="statusController" :history-section="sectionDiffSection"
        @restored="loadTimeline" @settings-saved="refreshAfterSettingsSave"
        @reverted="refreshBudAndTimeline" @confirm-delete="deleteBud"
      />
    </div>

    <BUDDetailChatPanel
      v-if="bud"
      :chat="chat" :section-label="currentSectionLabel" :needs-design-generation="needsDesignGeneration"
      :selected-design-id="designPanel?.activeDesignTab"
      @select-design="designPanel?.setActiveDesignTab($event)" @open-autogen-settings="skillSettingsOpen = true"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import BUDActivitySection from '@/components/buds/BUDActivitySection.vue'
import BUDBugsPanel from '@/components/buds/BUDBugsPanel.vue'
import BUDEstimationSection from '@/components/buds/BUDEstimationSection.vue'
import BUDHeader from '@/components/buds/BUDHeader.vue'
import BUDSectionToolbar from '@/components/buds/BUDSectionToolbar.vue'
import BUDWorkflowActions from '@/components/buds/BUDWorkflowActions.vue'
import BUDAgentBanners from '@/components/buds/detail/BUDAgentBanners.vue'
import BUDDetailChatPanel from '@/components/buds/detail/BUDDetailChatPanel.vue'
import BUDDetailDialogs from '@/components/buds/detail/BUDDetailDialogs.vue'
import BUDDetailLoadState from '@/components/buds/detail/BUDDetailLoadState.vue'
import BUDDetailsPanel from '@/components/buds/detail/BUDDetailsPanel.vue'
import BUDDetailTabBar from '@/components/buds/detail/BUDDetailTabBar.vue'
import BUDDetailTabPanels from '@/components/buds/detail/BUDDetailTabPanels.vue'
import BUDExternalLlmCallout from '@/components/buds/detail/BUDExternalLlmCallout.vue'
import BUDStageStepper from '@/components/buds/detail/BUDStageStepper.vue'
import { useBudAgentTracking } from '@/composables/useBudAgentTracking'
import { useBudDetailActions } from '@/composables/useBudDetailActions'
import { useBudDetailChat } from '@/composables/useBudDetailChat'
import { useBudDetailLoader } from '@/composables/useBudDetailLoader'
import { useBudDetailTabs } from '@/composables/useBudDetailTabs'
import { useBudHistoryDrawer } from '@/composables/useBudHistoryDrawer'
import { useBudSectionEditors } from '@/composables/useBudSectionEditors'
import { useBudSectionFiles } from '@/composables/useBudSectionFiles'
import { useBudStatusTransitions } from '@/composables/useBudStatusTransitions'
import { useBudTimeline } from '@/composables/useBudTimeline'
import { usePermissions } from '@/composables/usePermissions'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import { useAuthStore } from '@/stores/auth'
import { useBUDStore } from '@/stores/bud'
import { useBudLinkedFeaturesStore } from '@/stores/budLinkedFeatures'
import { BUD_STATUS_LABELS, type BUDStatus } from '@/types'
import { STATUS_TAB_MAP, canMoveBud, nextStage } from '@/utils/budDetail'

const budStore = useBUDStore()
const linkedFeaturesStore = useBudLinkedFeaturesStore()
const authStore = useAuthStore()
const { hasPermission } = usePermissions()
const { phaseOrder } = usePhaseOrder()

// The store keeps currentBUD to the BUD this page navigated to.
const bud = computed(() => budStore.currentBUD)
const canEditBud = computed(() => hasPermission('buds:edit'))
const canApprove = computed(() => ['tech_lead', 'manager', 'org_owner'].includes(authStore.user?.role ?? ''))
const isCurrentAssignee = computed(() => bud.value?.assignee_id != null && authStore.user?.id === bud.value.assignee_id)
// Every stage agent off (none set is the default): the person drives the BUD from their own AI.
const isExternalLlmMode = computed(() => {
  const phases = bud.value?.auto_generate_phases
  return Boolean(bud.value) && (!phases || !Object.values(phases).some(Boolean))
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
const dialogs = ref<InstanceType<typeof BUDDetailDialogs> | null>(null)
const designPanel = computed(() => panelsRef.value?.designPanel ?? null)
const estimationRef = ref<InstanceType<typeof BUDEstimationSection> | null>(null)
const reloadEstimates = (): void => void estimationRef.value?.loadEstimates()

const { agentLocked, agentRunning, generatingDesigns } = useBudAgentTracking(bud, workflowRef, () => {
  // An agent finished: the PM agent rewrites linked features on every run.
  void loadTimeline()
  reloadEstimates()
  if (bud.value) void linkedFeaturesStore.fetch(bud.value.id)
})
const { downloadSection, importSection } = useBudSectionFiles(bud, () => designPanel.value?.activeDesignObj)

const statusController = useBudStatusTransitions({
  getBud: () => bud.value,
  setActiveTab: (tab) => { activeTab.value = tab },
  getStatusTabMap: () => STATUS_TAB_MAP,
  triggerDesignGeneration: () => designPanel.value?.triggerDesignGeneration(),
  reloadTimeline: () => loadTimeline(),
})
const { updateStatus, changingStatus, cancelRunningAgent, cancellingAgent, cancelDesign, cancellingDesignId } =
  statusController

const statusItems = computed(() => phaseOrder.value.map(s => ({ title: BUD_STATUS_LABELS[s], value: s })))
const nextStatus = computed(() => (bud.value ? nextStage(phaseOrder.value, bud.value.status) : null))
const canMoveTo = (to: BUDStatus): boolean => !!bud.value && canMoveBud(hasPermission, bud.value.status, to)

const { requirements, techSpec, isEditing, toggleEdit, syncEditor } =
  useBudSectionEditors(bud, activeTab, currentSectionEditable, () => designPanel.value)

const chat = useBudDetailChat({
  bud, activeTab, currentSection, chatable: currentSectionChatable, agentLocked,
  getDesignPanel: () => designPanel.value, syncEditor,
})
const { chatOpen, chatMessages, loadChatHistory, startNewSession, enrichWithAI, openTechSpecChat } = chat

const { reload } = useBudDetailLoader({
  bud, activeTab, startNewSession, loadChatHistory, loadTimeline, reloadEstimates,
  onLearningRecorded: () => { learningRefreshKey.value += 1 },
})

const { refreshBudAndTimeline, refreshAfterSettingsSave, saveTitle, changeAssignee, changePriority, deleteBud } =
  useBudDetailActions(bud, loadTimeline)
</script>

<style scoped src="./bud-detail-page.css"></style>
