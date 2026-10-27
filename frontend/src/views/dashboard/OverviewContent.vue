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

<!-- The dashboard's default view: key numbers, then work (flow, attention,
     agents) beside people (setup, time off, team). One column on narrow
     screens, people cards after the work cards. -->
<template>
  <div class="overview">
    <KpiTiles :kpis="overview.kpis.value" />
    <AppCallout v-if="overview.error.value" variant="error">{{ overview.error.value }}</AppCallout>
    <div class="overview__grid">
      <div class="overview__col">
        <FlowPanel :stages="overview.stages.value" />
        <AttentionPanel :items="overview.attention.value" :pending-leave="overview.pendingLeave.value" />
        <AgentActivityPanel :activity="treeData?.agent_activity ?? []" />
      </div>
      <div class="overview__col">
        <SetupCard />
        <TimeOffPanel :entries="overview.timeOff.value" />
        <TeamPanel
          :members="treeData?.members ?? []"
          :quiz-playable="quizPlayable"
          :streak="streak"
          @quiz="emit('quiz')"
          @games="emit('games')"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
import AgentActivityPanel from '@/components/dashboard/AgentActivityPanel.vue'
import AttentionPanel from '@/components/dashboard/AttentionPanel.vue'
import FlowPanel from '@/components/dashboard/FlowPanel.vue'
import KpiTiles from '@/components/dashboard/KpiTiles.vue'
import SetupCard from '@/components/dashboard/SetupCard.vue'
import TeamPanel from '@/components/dashboard/TeamPanel.vue'
import TimeOffPanel from '@/components/dashboard/TimeOffPanel.vue'
import type { useDashboardOverview } from '@/composables/useDashboardOverview'
import type { TreeData } from '@/types/dashboard'

defineProps<{
  overview: ReturnType<typeof useDashboardOverview>
  treeData: TreeData | null
  quizPlayable: boolean
  streak: number
}>()

const emit = defineEmits<{ quiz: []; games: [] }>()
</script>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.overview__grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
.overview__col {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
@media (max-width: 1100px) {
  .overview__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
