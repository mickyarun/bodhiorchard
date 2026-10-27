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

<!-- Dashboard. Overview (the default) is a scrolling page of cards; Graph
     and Garden are full-height canvases over the same code map. -->
<template>
  <div class="dashboard" :class="{ 'dashboard--canvas': viewMode !== 'overview' }">
    <DashboardHeader
      v-model="viewMode"
      :in-flight="overview.canViewBuds.value ? overview.inFlightCount.value : null"
      :people="overview.peopleInFlight.value"
      :standup-open="showStandup"
      :can-create="canCreateBuds"
      @standup="showStandup = !showStandup"
      @new-bud="showCreate = true"
    />

    <div class="dashboard__body">
      <!-- Running races and games, over whichever view is showing. -->
      <div class="dashboard__live"><LiveMatchesPanel /></div>

      <OverviewContent
        v-if="viewMode === 'overview'"
        :can-view-buds="overview.canViewBuds.value"
        :kpis="overview.kpis.value"
        :stages="overview.stages.value"
        :attention="overview.attention.value"
        :pending-leave="overview.pendingLeave.value"
        :time-off="overview.timeOff.value"
        :time-off-error="overview.timeOffError.value"
        :loading="overview.loading.value"
        :bud-error="overview.error.value"
        :code-map="store.treeData"
        :code-map-error="store.error"
        :code-map-as-of="store.loadedAt"
        :quiz-playable="quizPlayable"
        :streak="minigames.streakCount"
        @quiz="showQuiz = true"
        @games="showGames = true"
      />
      <template v-else>
        <CanvasToolbar
          v-model:visible-repos="repos.visibleRepos.value"
          :mode="viewMode"
          :data="repos.displayData.value"
          :repo-names="repos.repoNames.value"
          :relations-on="showRelations"
          :graph-has-selection="graphHasSelection"
          @toggle-all-repos="repos.toggleAll"
          @toggle-relations="toggleRelations"
          @graph-back="stageRef?.backToOverview()"
        />
        <AppCallout v-if="store.error" variant="error">{{ store.error }}</AppCallout>
        <CanvasStage
          ref="stageRef"
          :mode="viewMode"
          :loading="store.loading"
          :data="repos.displayData.value"
          :tree-data="store.treeData"
          :visible-repos="repos.visibleRepos.value"
          :in-control="takeover.inControl.value"
          @graph-selection="graphHasSelection = $event"
          @zone="onZone"
        />
      </template>

    </div>

    <StandupDock v-model="showStandup" />

    <MiniGameHub v-model="showGames" />
    <QuizHub v-model="showQuiz" />
    <BUDCreateDialog v-model="showCreate" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import BUDCreateDialog from '@/components/buds/BUDCreateDialog.vue'
import CanvasToolbar from '@/components/dashboard/CanvasToolbar.vue'
import DashboardHeader from '@/components/dashboard/DashboardHeader.vue'
import LiveMatchesPanel from '@/components/minigames/LiveMatchesPanel.vue'
import MiniGameHub from '@/components/minigames/MiniGameHub.vue'
import QuizHub from '@/components/quiz/QuizHub.vue'
import StandupDock from '@/components/standup/StandupDock.vue'
import { useDashboardOverview } from '@/composables/useDashboardOverview'
import { useDashboardViewMode } from '@/composables/useDashboardViewMode'
import { useGardenTakeover } from '@/composables/useGardenTakeover'
import { usePermissions } from '@/composables/usePermissions'
import { useQuizSocket } from '@/composables/useQuizSocket'
import { useRepoFilter } from '@/composables/useRepoFilter'
import { useDashboardStore } from '@/stores/dashboard'
import { useMinigamesStore } from '@/stores/minigames'
import { useQuizStore } from '@/stores/quiz'
import CanvasStage from './CanvasStage.vue'
import OverviewContent from './OverviewContent.vue'

const store = useDashboardStore()
const minigames = useMinigamesStore()
const quizStore = useQuizStore()
const { canCreateBuds } = usePermissions()
const viewMode = useDashboardViewMode()
const overview = useDashboardOverview()
const repos = useRepoFilter(computed(() => store.treeData))

const showStandup = ref(false)
const showGames = ref(false)
const showQuiz = ref(false)
const showCreate = ref(false)
const showRelations = ref(false)
const graphHasSelection = ref(false)
const stageRef = ref<InstanceType<typeof CanvasStage> | null>(null)

const takeover = useGardenTakeover(stageRef, () => viewMode.value === 'garden')
// Keep the quiz button live as quizzes open and reveal over the socket.
useQuizSocket()
const quizPlayable = computed(() => !!quizStore.active && !quizStore.active.alreadyAnswered)

watch(viewMode, () => {
  graphHasSelection.value = false
  showRelations.value = false
})

function toggleRelations(): void {
  showRelations.value = stageRef.value?.toggleArcs() ?? !showRelations.value
}

function onZone(zone: string, entered: boolean): void {
  if (zone === 'pavilion') showStandup.value = entered
}

onMounted(() => {
  void store.fetchTreeData()
  void minigames.fetchStatus()
  // Load the reveal too when already answered, so the hub opens on results.
  void quizStore.fetchActive().then(() => {
    if (quizStore.active?.alreadyAnswered) void quizStore.fetchReveal(quizStore.active.id)
  })
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 24px;
  min-height: 100%;
  padding: 28px 36px 40px;
  background: rgb(var(--v-theme-background));
}
.dashboard--canvas {
  height: 100%;
  gap: 16px;
  padding-bottom: 16px;
}
.dashboard__body {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1 1 auto;
  min-height: 0;
}
@media (max-width: 600px) {
  .dashboard {
    padding: 20px 16px 32px;
  }
}
</style>
