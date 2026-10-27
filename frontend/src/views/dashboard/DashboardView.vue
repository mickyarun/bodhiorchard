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
      :greeting="greeting"
      :subtitle="subtitle"
      :standup-open="showStandup"
      :can-create="canCreateBuds"
      @standup="showStandup = !showStandup"
      @new-bud="showCreate = true"
    />

    <div class="dashboard__body">
      <OverviewContent
        v-if="viewMode === 'overview'"
        :overview="overview"
        :tree-data="store.treeData"
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

    <!-- Pinned to the viewport's right edge so it stays in view while the
         overview scrolls. -->
    <div v-if="showStandup" class="dashboard__standup">
      <Transition name="slide-panel" appear>
        <StandupPanel @close="showStandup = false" />
      </Transition>
    </div>

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
import MiniGameHub from '@/components/minigames/MiniGameHub.vue'
import QuizHub from '@/components/quiz/QuizHub.vue'
import StandupPanel from '@/components/standup/StandupPanel.vue'
import { useDashboardOverview } from '@/composables/useDashboardOverview'
import { useDashboardViewMode } from '@/composables/useDashboardViewMode'
import { useGardenTakeover } from '@/composables/useGardenTakeover'
import { usePermissions } from '@/composables/usePermissions'
import { useQuizSocket } from '@/composables/useQuizSocket'
import { useRepoFilter } from '@/composables/useRepoFilter'
import { useAuthStore } from '@/stores/auth'
import { useDashboardStore } from '@/stores/dashboard'
import { useMinigamesStore } from '@/stores/minigames'
import { useQuizStore } from '@/stores/quiz'
import { greetingFor } from '@/utils/dashboardOverview'
import { firstName } from '@/utils/leave'
import CanvasStage from './CanvasStage.vue'
import OverviewContent from './OverviewContent.vue'

const store = useDashboardStore()
const auth = useAuthStore()
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

const greeting = computed(() => {
  const name = auth.user?.name ? `, ${firstName(auth.user.name)}` : ''
  return `${greetingFor(new Date().getHours())}${name}`
})
const subtitle = computed(() => {
  const today = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })
  const people = overview.peopleInFlight.value
  const across = people ? ` across ${people === 1 ? '1 person' : `${people} people`}` : ''
  return `${today} · ${overview.inFlightCount.value} BUDs in flight${across}`
})

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
.dashboard__standup {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(376px, 100%);
  /* Above the phone top bar, below the navigation drawer. */
  z-index: 1005;
}
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: transform var(--dur-mid) var(--ease-out), opacity var(--dur-mid) var(--ease-out);
}
.slide-panel-enter-from,
.slide-panel-leave-to {
  transform: translateX(40px);
  opacity: 0;
}
@media (max-width: 600px) {
  .dashboard {
    padding: 20px 16px 32px;
  }
}
</style>
