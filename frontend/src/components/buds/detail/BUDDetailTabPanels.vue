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

<!-- The content of each BUD section tab. Every v-tabs-window-item value
     must match a tab value from detailTabs() (utils/budDetail.ts), or the
     tab opens blank. -->
<template>
  <div class="tab-panels">
    <v-tabs-window v-model="tab">
      <v-tabs-window-item value="requirements">
        <BUDRequirementsTab
          :bud="bud"
          :editing="requirementsEditing"
          :edit-value="requirementsDraft"
          :agent-locked="agentLocked"
          @update:edit-value="requirementsDraft = $event"
          @save="requirements.save"
          @start-edit="requirements.toggle"
          @enrich="emit('enrich')"
          @features-changed="emit('timeline-changed')"
        />
      </v-tabs-window-item>

      <!-- Eager, so the panel's designAvailable watcher is live from the
           start and generation auto-starts the moment the BUD enters
           Design, whichever tab is open. -->
      <v-tabs-window-item value="design" eager>
        <BUDDesignPanel
          ref="designPanel"
          :bud-id="bud.id"
          :editable="bud.status === 'design'"
          @chat-message="emit('chat-message', $event)"
          @switch-to-design="tab = 'design'"
          @design-tab-change="emit('design-tab-change')"
        />
      </v-tabs-window-item>

      <v-tabs-window-item value="tech-spec">
        <BUDTechSpecTab
          :bud="bud"
          :editing="techSpecEditing"
          :edit-value="techSpecDraft"
          @update:edit-value="techSpecDraft = $event"
          @save="techSpec.save"
          @start-edit="techSpec.toggle"
          @generate="emit('open-tech-spec-chat')"
          @refresh-bud="refreshBud"
        />
      </v-tabs-window-item>

      <v-tabs-window-item value="development">
        <BUDTodoBoard :bud-id="bud.id" />
        <BUDPRChecklist v-if="bud.impacted_repos?.length" :bud-id="bud.id" />
        <BUDDevelopmentPanel
          :bud-id="bud.id"
          :bud-number="bud.bud_number"
          :has-tech-spec="!!bud.tech_spec_md"
          :impacted-repos="bud.impacted_repos"
          @download-tech-spec="emit('download-tech-spec')"
          @refresh-bud="refreshBud"
        />
      </v-tabs-window-item>

      <v-tabs-window-item value="code-review">
        <BUDCodeReviewTab :bud-id="bud.id" :status="bud.status" @transitioned="emit('refresh')" />
      </v-tabs-window-item>

      <v-tabs-window-item value="testing">
        <BUDQAPanel
          :bud-id="bud.id"
          :bud-number="bud.bud_number"
          :test-plan-md="bud.test_plan_md"
          :impacted-repos="bud.impacted_repos"
          :active-agent-task="bud.active_agent_task"
        />
      </v-tabs-window-item>

      <v-tabs-window-item v-if="uatEnabled" value="uat">
        <BUDReleaseStagePanel
          :bud-id="bud.id"
          :bud-number="bud.bud_number"
          stage="uat"
          :has-stage-branch-configured="hasUatBranchConfigured"
          :impacted-repos="bud.impacted_repos"
          :branch-overrides="bud.branch_overrides"
          @refresh-bud="refreshBud"
        />
      </v-tabs-window-item>

      <v-tabs-window-item value="prod">
        <BUDReleaseStagePanel
          :bud-id="bud.id"
          :bud-number="bud.bud_number"
          stage="prod"
          :has-stage-branch-configured="hasMainBranchConfigured"
          :impacted-repos="bud.impacted_repos"
          :branch-overrides="bud.branch_overrides"
          @refresh-bud="refreshBud"
        />
      </v-tabs-window-item>

      <v-tabs-window-item v-if="isClosed" value="closed">
        <BUDClosedTab :bud="bud" :timeline-events="timelineEvents" />
      </v-tabs-window-item>

      <v-tabs-window-item v-if="hasLearning" value="learnings">
        <LearningsPanel :bud-id="bud.id" :refresh-key="learningRefreshKey" :can-regenerate="canRegenerateLearning" />
      </v-tabs-window-item>
    </v-tabs-window>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import BUDClosedTab from '@/components/buds/BUDClosedTab.vue'
import BUDDesignPanel from '@/components/buds/BUDDesignPanel.vue'
import BUDDevelopmentPanel from '@/components/buds/BUDDevelopmentPanel.vue'
import BUDPRChecklist from '@/components/buds/BUDPRChecklist.vue'
import BUDQAPanel from '@/components/buds/BUDQAPanel.vue'
import BUDReleaseStagePanel from '@/components/buds/BUDReleaseStagePanel.vue'
import BUDRequirementsTab from '@/components/buds/BUDRequirementsTab.vue'
import BUDTechSpecTab from '@/components/buds/BUDTechSpecTab.vue'
import BUDTodoBoard from '@/components/buds/BUDTodoBoard.vue'
import LearningsPanel from '@/components/buds/LearningsPanel.vue'
import BUDCodeReviewTab from './BUDCodeReviewTab.vue'
import { useBudReleaseBranches } from '@/composables/useBudReleaseBranches'
import type { useMarkdownSection } from '@/composables/useMarkdownSection'
import { useBUDStore } from '@/stores/bud'
import type { BUDDocument, TimelineEvent } from '@/types'

type MarkdownEditor = ReturnType<typeof useMarkdownSection>

const props = defineProps<{
  bud: BUDDocument
  /** The page's Requirements and Tech spec editors (one instance each for the page's life). */
  requirements: MarkdownEditor
  techSpec: MarkdownEditor
  agentLocked: boolean
  uatEnabled: boolean
  isClosed: boolean
  hasLearning: boolean
  timelineEvents: TimelineEvent[]
  /** Bumped when a learning recap lands so the Learnings panel refetches. */
  learningRefreshKey: number
}>()

const emit = defineEmits<{
  enrich: []
  'open-tech-spec-chat': []
  'chat-message': [message: { role: 'ai'; text: string }]
  'design-tab-change': []
  'download-tech-spec': []
  /** Refetch the BUD and its timeline. */
  refresh: []
  'timeline-changed': []
}>()

const tab = defineModel<string>('tab', { required: true })
// Stable refs from the page's editors, so destructuring keeps reactivity.
const { editing: requirementsEditing, editValue: requirementsDraft } = props.requirements
const { editing: techSpecEditing, editValue: techSpecDraft } = props.techSpec

const budStore = useBUDStore()
const designPanel = ref<InstanceType<typeof BUDDesignPanel> | null>(null)
const { hasUatBranchConfigured, hasMainBranchConfigured } = useBudReleaseBranches(computed(() => props.bud))

// Regenerating the recap only makes sense for a closed BUD that opted into
// the close-time agent; that's the backend's gate too, so no button that
// could only 409.
const canRegenerateLearning = computed(
  () => props.bud.status === 'closed' && Boolean(props.bud.auto_generate_phases?.closed),
)

const budId = toRef(() => props.bud.id)
function refreshBud(): void {
  void budStore.refreshBUDIfCurrent(budId.value)
}

defineExpose({ designPanel })
</script>

<style scoped>
.tab-panels {
  min-height: 300px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
</style>
