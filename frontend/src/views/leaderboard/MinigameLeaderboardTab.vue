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

<template>
  <div>
    <v-skeleton-loader
      v-if="loading && entries.length === 0"
      type="list-item-avatar-two-line@5"
    />

    <div v-else-if="entries.length === 0" class="pa-6 text-center text-medium-emphasis">
      No scores yet for {{ gameName }}. Play it in the garden to claim the top spot! 🌱
    </div>

    <template v-else>
      <div class="lb-content">
        <!-- Podium — shared with the XP and race tabs. -->
        <LeaderboardPodium v-if="entries.length >= 3" :entries="podiumEntries" class="mb-6" />

        <!-- Full ranked list -->
        <v-card color="surface">
          <v-list density="comfortable" class="bg-transparent">
            <v-list-item
              v-for="(row, i) in entries"
              :key="row.user_id"
              :class="{ 'lb-row--me': row.user_id === currentUserId }"
              class="lb-row"
            >
              <template #prepend>
                <div class="lb-row__rank">
                  <span v-if="i < 3" class="lb-row__medal">{{ MEDALS[i] }}</span>
                  <span v-else class="text-body-2 text-medium-emphasis">#{{ i + 1 }}</span>
                </div>
                <v-avatar size="32" color="primary" variant="tonal" class="mr-3">
                  <span class="text-caption font-weight-bold">{{ initials(row.user_name) }}</span>
                </v-avatar>
              </template>
              <v-list-item-title class="font-weight-medium">
                {{ row.user_name }}
              </v-list-item-title>
              <v-list-item-subtitle v-if="isOrgAdmin" class="text-caption">
                {{ row.plays }} {{ row.plays === 1 ? 'play' : 'plays' }}
              </v-list-item-subtitle>
              <template #append>
                <span class="bo-display font-weight-bold game-score">
                  {{ row.best_score.toLocaleString() }}
                </span>
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMinigamesStore } from '@/stores/minigames'
import { useAuthStore } from '@/stores/auth'
import { usePermissions } from '@/composables/usePermissions'
import LeaderboardPodium, { type PodiumEntry } from '@/components/leaderboard/LeaderboardPodium.vue'

const props = defineProps<{
  game: string
  gameName: string
}>()

const store = useMinigamesStore()
const authStore = useAuthStore()
const { isOrgAdmin } = usePermissions()
const loading = ref(false)

const MEDALS = ['🥇', '🥈', '🥉']

const currentUserId = computed(() => authStore.user?.id || '')
const entries = computed(() => store.leaderboards[props.game] ?? [])

async function load(game: string): Promise<void> {
  loading.value = true
  try {
    await store.fetchLeaderboard(game)
  } finally {
    loading.value = false
  }
}

watch(() => props.game, (g) => { void load(g) })
onMounted(() => { void load(props.game) })

function initials(name: string): string {
  if (!name) return '?'
  return name.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2) || '?'
}

// Top-3 mapped to the shared podium. Best score is a neutral achievement
// metric (games award NO XP), so it uses the 'ink' figure kind — gold stays
// reserved for the XP board.
const podiumEntries = computed<PodiumEntry[]>(() =>
  entries.value.slice(0, 3).map((row) => ({
    name: row.user_name,
    figure: row.best_score.toLocaleString(),
    figureKind: 'ink',
    // Play count is admin-only detail — hidden from ordinary players.
    meta: isOrgAdmin.value ? `${row.plays} ${row.plays === 1 ? 'play' : 'plays'}` : undefined,
    isMe: row.user_id === currentUserId.value,
  })),
)
</script>

<style scoped>
/* Focused centred column — matches the XP and race tabs. */
.lb-content {
  max-width: 820px;
  margin: 0 auto;
}

.game-score {
  color: rgb(var(--v-theme-on-surface));
  font-size: 1.05rem;
  font-variant-numeric: tabular-nums;
}

.lb-row__rank { min-width: 36px; text-align: center; margin-right: 8px; }
.lb-row__medal { font-size: 20px; }

.lb-row--me {
  background: rgba(var(--v-theme-primary), 0.08) !important;
  border-left: 3px solid rgb(var(--v-theme-primary));
}
</style>
