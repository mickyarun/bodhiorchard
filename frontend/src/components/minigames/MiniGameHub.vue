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

  MiniGameHub — garden games dialog: pick a game, beat your best, climb
  the org leaderboard, and keep your daily play streak alive.

  Mini-games award NO XP (XP is for real development work). The reward is
  your best score + leaderboard rank.
-->
<template>
  <v-dialog :model-value="modelValue" max-width="480" @update:model-value="close">
    <v-card rounded="lg">
      <v-card-title class="d-flex align-center ga-2">
        <v-icon icon="mdi-gamepad-variant-outline" />
        Garden Games
        <v-spacer />
        <v-chip size="small" color="warning" variant="tonal" prepend-icon="mdi-fire">
          {{ store.streakCount }}-day streak
        </v-chip>
      </v-card-title>

      <v-card-text>
        <!-- Game picker + leaderboard -->
        <template v-if="!activeGame">
          <p class="text-body-2 text-medium-emphasis mb-3">
            Play daily to keep your streak alive and top the leaderboard. No XP —
            just bragging rights.
          </p>
          <v-list density="comfortable">
            <v-list-item
              v-for="game in store.games"
              :key="game.key"
              rounded="lg"
              :title="game.name"
              @click="openGame(game.key)"
            >
              <template #prepend>
                <v-icon :icon="GAME_ICONS[game.key] ?? 'mdi-gamepad'" />
              </template>
              <template #subtitle>
                Best {{ game.best_score }} / {{ game.max_score }}
                <span v-if="game.played_today"> · played today</span>
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
        <template v-else-if="playing">
          <FishingGame v-if="activeGame === 'fishing'" @finished="onFinished" />
          <PollenPop v-else-if="activeGame === 'pollen_pop'" @finished="onFinished" />
        </template>

        <!-- Result + leaderboard for the active game -->
        <template v-else>
          <v-alert
            class="mb-3"
            density="compact"
            :type="lastResult?.is_new_best ? 'success' : 'info'"
            variant="tonal"
          >
            <template v-if="lastResult?.is_new_best">
              🏆 New personal best: {{ lastResult.score }}!
              · 🔥 {{ lastResult.current_streak }}-day streak
            </template>
            <template v-else>
              Scored {{ lastResult?.score }} · best {{ lastResult?.best_score }}
              · 🔥 {{ lastResult?.current_streak }}-day streak
            </template>
          </v-alert>

          <div class="text-overline mb-1">{{ activeGameName }} leaderboard</div>
          <v-list density="compact" class="pa-0">
            <v-list-item
              v-for="(row, i) in activeLeaderboard"
              :key="row.user_id"
              class="px-2"
            >
              <template #prepend>
                <span class="text-body-2 font-weight-bold mr-3" style="width: 20px">
                  {{ i + 1 }}
                </span>
              </template>
              <v-list-item-title class="text-body-2">{{ row.user_name }}</v-list-item-title>
              <template #append>
                <span class="text-body-2 font-weight-medium">{{ row.best_score }}</span>
              </template>
            </v-list-item>
            <v-list-item v-if="activeLeaderboard.length === 0">
              <v-list-item-title class="text-caption text-medium-emphasis">
                No scores yet — you could be first!
              </v-list-item-title>
            </v-list-item>
          </v-list>

          <v-btn class="mt-3" variant="tonal" block @click="replay">Play again</v-btn>
        </template>
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
import { computed, ref, watch } from 'vue'
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
const playing = ref(false)
const lastResult = ref<MinigameScoreResult | null>(null)

const activeGameName = computed(
  () => store.games.find((g) => g.key === activeGame.value)?.name ?? '',
)
const activeLeaderboard = computed(() =>
  activeGame.value ? (store.leaderboards[activeGame.value] ?? []) : [],
)

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      lastResult.value = null
      activeGame.value = null
      playing.value = false
      void store.fetchStatus()
    }
  },
)

function openGame(key: string): void {
  activeGame.value = key
  playing.value = true
  void store.fetchLeaderboard(key)
}

async function onFinished(score: number): Promise<void> {
  if (!activeGame.value) return
  lastResult.value = await store.submitScore(activeGame.value, score)
  playing.value = false
}

function replay(): void {
  if (activeGame.value) openGame(activeGame.value)
}

function backToList(): void {
  activeGame.value = null
  playing.value = false
}

function close(value: boolean): void {
  if (!value) emit('update:modelValue', false)
}
</script>
