<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  MiniGameHub — garden games dialog with the daily streak.

  First play of each game per day earns XP; any play keeps the daily
  streak alive. Game components emit `finished(score)`; the hub submits
  the score and shows the award.
-->
<template>
  <v-dialog :model-value="modelValue" max-width="460" @update:model-value="close">
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center ga-2">
        <v-icon icon="mdi-gamepad-variant-outline" />
        Garden Games
        <v-spacer />
        <v-chip size="small" color="warning" variant="tonal" prepend-icon="mdi-fire">
          {{ store.streakCount }} day streak
        </v-chip>
      </v-card-title>

      <v-card-text>
        <!-- Game picker -->
        <template v-if="!activeGame">
          <p class="text-body-2 text-medium-emphasis mb-4">
            Play once a day to keep your streak alive. Best: {{ store.streakBest }} days.
          </p>
          <v-list density="comfortable">
            <v-list-item
              v-for="game in store.games"
              :key="game.key"
              rounded="lg"
              :title="game.name"
              :subtitle="game.played_today
                ? 'Played today — replay for fun'
                : `Up to ${game.max_xp} XP today`"
              @click="activeGame = game.key"
            >
              <template #prepend>
                <v-icon :icon="GAME_ICONS[game.key] ?? 'mdi-gamepad'" />
              </template>
              <template #append>
                <v-icon
                  v-if="game.played_today"
                  icon="mdi-check-circle"
                  color="success"
                  size="small"
                />
              </template>
            </v-list-item>
          </v-list>
        </template>

        <!-- Active game -->
        <FishingGame v-else-if="activeGame === 'fishing'" @finished="onFinished" />
        <PollenPop v-else-if="activeGame === 'pollen_pop'" @finished="onFinished" />

        <!-- Result toastlet -->
        <v-alert
          v-if="lastResult"
          class="mt-3"
          density="compact"
          :type="lastResult.first_play_today ? 'success' : 'info'"
          variant="tonal"
        >
          <template v-if="lastResult.first_play_today">
            +{{ lastResult.xp_awarded }} XP
            <template v-if="lastResult.level_changed"> — level up!</template>
            · 🔥 {{ lastResult.streak_count }}-day streak
          </template>
          <template v-else>
            Streak safe — 🔥 {{ lastResult.streak_count }} days (XP already earned today)
          </template>
        </v-alert>
      </v-card-text>

      <v-card-actions>
        <v-btn v-if="activeGame" variant="text" @click="backToList">Back</v-btn>
        <v-spacer />
        <v-btn variant="text" @click="close(false)">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useMinigamesStore, type MinigameScoreResult } from '@/stores/minigames'
import FishingGame from './FishingGame.vue'
import PollenPop from './PollenPop.vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const GAME_ICONS: Record<string, string> = {
  fishing: 'mdi-fish',
  pollen_pop: 'mdi-flower-pollen',
}

const store = useMinigamesStore()
const activeGame = ref<string | null>(null)
const lastResult = ref<MinigameScoreResult | null>(null)

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      lastResult.value = null
      activeGame.value = null
      void store.fetchStatus()
    }
  },
)

async function onFinished(score: number): Promise<void> {
  if (!activeGame.value) return
  lastResult.value = await store.submitScore(activeGame.value, score)
  activeGame.value = null
}

function backToList(): void {
  activeGame.value = null
}

function close(value: boolean): void {
  if (!value) emit('update:modelValue', false)
}
</script>
