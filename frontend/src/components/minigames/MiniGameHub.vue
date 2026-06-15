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

  MiniGameHub — garden games arcade: cover-art game cards, medal
  leaderboard, celebratory results, daily play streak. No XP — the
  reward is your best score and the org leaderboard.
-->
<template>
  <v-dialog :model-value="modelValue" max-width="520" @update:model-value="close">
    <v-card rounded="xl" class="hub">
      <!-- Header -->
      <div class="hub__header px-5 pt-4 pb-3 d-flex align-center ga-3">
        <span class="hub__logo">🎮</span>
        <div>
          <div class="text-h6 font-weight-bold">Garden Games</div>
          <div class="text-caption text-medium-emphasis">
            Play daily · top the leaderboard
          </div>
        </div>
        <v-spacer />
        <div class="hub__streak" :class="{ 'hub__streak--lit': store.streakCount > 0 }">
          <span class="hub__flame">🔥</span>
          <span class="hub__streak-num">{{ store.streakCount }}</span>
          <span class="hub__streak-label">day streak</span>
        </div>
      </div>

      <v-card-text class="px-5 pb-5 pt-2">
        <!-- ── Game picker: cover cards ── -->
        <template v-if="!activeGame">
          <div class="hub__cards">
            <button
              v-for="game in store.games"
              :key="game.key"
              class="game-card"
              :class="`game-card--${game.key}`"
              @click="openGame(game.key)"
            >
              <span class="game-card__art">{{ GAME_ART[game.key] ?? '🎲' }}</span>
              <span class="game-card__name">{{ game.name }}</span>
              <span class="game-card__best">
                Best <strong>{{ game.best_score }}</strong>
              </span>
              <span v-if="game.played_today" class="game-card__badge">✓ played today</span>
              <span v-else class="game-card__badge game-card__badge--go">▶ play</span>
            </button>
          </div>
        </template>

        <!-- ── Active game ── -->
        <template v-else-if="playing">
          <FishingGame v-if="activeGame === 'fishing'" @finished="onFinished" />
          <PollenPop v-else-if="activeGame === 'pollen_pop'" @finished="onFinished" />
          <FireflyFollow v-else-if="activeGame === 'firefly'" @finished="onFinished" />
        </template>

        <!-- ── Result + leaderboard ── -->
        <template v-else>
          <div
            class="result-banner mb-4"
            :class="lastResult?.is_new_best ? 'result-banner--best' : ''"
          >
            <span class="result-banner__emoji">
              {{ lastResult?.is_new_best ? '🏆' : '🌿' }}
            </span>
            <div>
              <div class="text-subtitle-1 font-weight-bold">
                <template v-if="lastResult?.is_new_best">
                  New personal best — {{ lastResult.score }}!
                </template>
                <template v-else>
                  Scored {{ lastResult?.score }} · best {{ lastResult?.best_score }}
                </template>
              </div>
              <div class="text-caption">
                🔥 {{ lastResult?.current_streak }}-day streak kept alive
              </div>
            </div>
          </div>

          <div class="board">
            <div class="board__title">{{ activeGameName }} · leaderboard</div>
            <div
              v-for="(row, i) in activeLeaderboard"
              :key="row.user_id"
              class="board__row"
              :class="{ 'board__row--top': i === 0 }"
            >
              <span class="board__rank">{{ MEDALS[i] ?? `${i + 1}` }}</span>
              <span class="board__name">{{ row.user_name }}</span>
              <span class="board__score">{{ row.best_score }}</span>
            </div>
            <div v-if="activeLeaderboard.length === 0" class="board__empty">
              No scores yet — you could be first! 🌱
            </div>
          </div>

          <v-btn class="mt-4" color="primary" rounded="lg" block size="large" @click="replay">
            Play again
          </v-btn>
        </template>
      </v-card-text>

      <v-card-actions class="px-5 pb-4 pt-0">
        <v-btn v-if="activeGame" variant="text" prepend-icon="mdi-arrow-left" @click="backToList">
          All games
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="close(false)">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMinigamesStore } from '@/stores/minigames'
import type { MinigameResult } from '@/multiplayer/MinigameRoomClient'
import FishingGame from './FishingGame.vue'
import PollenPop from './PollenPop.vue'
import FireflyFollow from './FireflyFollow.vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const GAME_ART: Record<string, string> = {
  fishing: '🎣',
  pollen_pop: '🌸',
  firefly: '✨',
}
const MEDALS = ['🥇', '🥈', '🥉']

const store = useMinigamesStore()
const activeGame = ref<string | null>(null)
const playing = ref(false)
const lastResult = ref<MinigameResult | null>(null)

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

async function onFinished(result: MinigameResult | null): Promise<void> {
  if (!activeGame.value) return
  // The score was already recorded server-side (via the multiplayer bridge);
  // the room handed back the outcome. Just show it and refresh the boards.
  lastResult.value = result
  playing.value = false
  await store.fetchLeaderboard(activeGame.value)
  void store.fetchStatus()
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

<style scoped>
.hub__logo {
  font-size: 30px;
}
.hub__streak {
  display: flex;
  align-items: baseline;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(255, 152, 0, 0.08);
  border: 1px solid rgba(255, 152, 0, 0.25);
  opacity: 0.65;
}
.hub__streak--lit {
  opacity: 1;
  background: rgba(255, 152, 0, 0.16);
  border-color: rgba(255, 152, 0, 0.5);
}
.hub__flame {
  font-size: 16px;
}
.hub__streak-num {
  font-size: 18px;
  font-weight: 800;
}
.hub__streak-label {
  font-size: 11px;
  opacity: 0.8;
}

/* ── Game cards ── */
.hub__cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.game-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 22px 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  color: inherit;
}
.game-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}
.game-card--fishing {
  background: linear-gradient(160deg, #15405a 0%, #1d6a86 60%, #2e94a6 100%);
}
.game-card--pollen_pop {
  background: linear-gradient(160deg, #3c5a23 0%, #5a7c2e 60%, #87a83c 100%);
}
.game-card--firefly {
  background: linear-gradient(160deg, #1a1840 0%, #3b2d6e 55%, #6a4fa0 100%);
}
.game-card__art {
  font-size: 44px;
  line-height: 1;
  filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.35));
}
.game-card__name {
  font-weight: 700;
  font-size: 15px;
  color: #fff;
}
.game-card__best {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.85);
}
.game-card__badge {
  margin-top: 6px;
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
}
.game-card__badge--go {
  background: rgba(255, 255, 255, 0.92);
  color: #1b3a22;
  font-weight: 700;
}

/* ── Result banner ── */
.result-banner {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(120, 200, 120, 0.1);
  border: 1px solid rgba(120, 200, 120, 0.25);
}
.result-banner--best {
  background: linear-gradient(120deg, rgba(255, 193, 7, 0.18), rgba(255, 152, 0, 0.1));
  border-color: rgba(255, 193, 7, 0.45);
  animation: best-pop 0.45s ease-out;
}
.result-banner__emoji {
  font-size: 34px;
}
@keyframes best-pop {
  0% { transform: scale(0.92); }
  60% { transform: scale(1.03); }
  100% { transform: scale(1); }
}

/* ── Leaderboard ── */
.board {
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.board__title {
  padding: 8px 14px;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.7;
  background: rgba(255, 255, 255, 0.04);
}
.board__row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
}
.board__row--top {
  background: rgba(255, 193, 7, 0.08);
}
.board__row + .board__row {
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}
.board__rank {
  width: 26px;
  text-align: center;
  font-size: 15px;
}
.board__name {
  flex: 1;
  font-size: 14px;
}
.board__score {
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.board__empty {
  padding: 14px;
  font-size: 13px;
  opacity: 0.7;
  text-align: center;
}
</style>
