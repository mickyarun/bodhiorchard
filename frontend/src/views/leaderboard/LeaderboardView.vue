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

<!-- Leaderboard: XP from real dev work, then each game's own board (quiz,
     both circuit distances and every registered mini game). Games never
     award XP. -->
<template>
  <AppPage title="Leaderboard" subtitle="XP comes only from real dev work. Games have their own boards and never award XP.">
    <v-tabs v-model="tab" color="primary" density="comfortable" show-arrows class="lb-page__tabs" aria-label="Boards">
      <v-tab v-for="t in tabs" :key="t.value" :value="t.value" class="lb-page__tab">{{ t.label }}</v-tab>
    </v-tabs>

    <v-tabs-window v-model="tab">
      <v-tabs-window-item value="xp"><XpLeaderboardTab /></v-tabs-window-item>
      <v-tabs-window-item value="quiz"><QuizLeaderboardTab /></v-tabs-window-item>
      <v-tabs-window-item value="race-100"><RaceLeaderboardTab :distance="100" /></v-tabs-window-item>
      <v-tabs-window-item value="race-200"><RaceLeaderboardTab :distance="200" /></v-tabs-window-item>
      <v-tabs-window-item v-for="game in minigamesStore.games" :key="game.key" :value="`game-${game.key}`">
        <MinigameLeaderboardTab :game="game.key" :game-name="game.name" />
      </v-tabs-window-item>
    </v-tabs-window>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppPage from '@/components/common/AppPage.vue'
import { useMinigamesStore } from '@/stores/minigames'
import MinigameLeaderboardTab from './MinigameLeaderboardTab.vue'
import QuizLeaderboardTab from './QuizLeaderboardTab.vue'
import RaceLeaderboardTab from './RaceLeaderboardTab.vue'
import XpLeaderboardTab from './XpLeaderboardTab.vue'

const minigamesStore = useMinigamesStore()

// One tab per board; mini games come from the registered games list.
const tab = ref('xp')
const tabs = computed(() => [
  { value: 'xp', label: 'XP' },
  { value: 'quiz', label: 'Quiz' },
  { value: 'race-100', label: 'Circuit · 1 lap' },
  { value: 'race-200', label: 'Circuit · 2 laps' },
  ...minigamesStore.games.map(g => ({ value: `game-${g.key}`, label: g.name })),
])

onMounted(() => void minigamesStore.fetchStatus())
</script>

<style scoped>
.lb-page__tabs {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
.lb-page__tab {
  font-size: 14px;
  font-weight: 500;
  min-width: 0;
  padding: 0 12px;
}
</style>
