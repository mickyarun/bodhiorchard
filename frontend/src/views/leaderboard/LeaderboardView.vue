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
  <v-container class="py-6" fluid>
    <div class="d-flex align-center mb-4">
      <v-icon icon="mdi-trophy" color="secondary" size="28" class="mr-2" />
      <div class="text-h5 font-weight-bold bo-display">Leaderboard</div>
      <v-spacer />
      <v-chip
        v-if="activeTab === 'xp'"
        variant="tonal"
        size="small"
        color="primary"
      >
        {{ entries.length }} members
      </v-chip>
    </div>

    <v-tabs v-model="activeTab" color="primary" density="comfortable" class="mb-4">
      <v-tab value="xp">XP</v-tab>
      <v-tab value="race-100">Circuit · 1 lap</v-tab>
      <v-tab value="race-200">Circuit · 2 laps</v-tab>
    </v-tabs>

    <v-window v-model="activeTab">
      <v-window-item value="race-100">
        <RaceLeaderboardTab :distance="100" />
      </v-window-item>
      <v-window-item value="race-200">
        <RaceLeaderboardTab :distance="200" />
      </v-window-item>
      <v-window-item value="xp">

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <div class="lb-content">
    <!-- Podium — top 3, shared with the race tabs. -->
    <LeaderboardPodium v-if="entries.length >= 3" :entries="podiumEntries" class="mb-8" />

    <!-- Full ranked list (all members) -->
    <v-card color="surface">
      <v-list density="comfortable" class="bg-transparent">
        <v-list-item
          v-for="(entry, i) in entries"
          :key="entry.user_id"
          :class="{ 'lb-row--me': entry.user_id === currentUserId }"
          class="lb-row"
        >
          <template #prepend>
            <div class="lb-row__rank">
              <span v-if="i < 3" class="lb-row__medal">{{ MEDALS[i] }}</span>
              <span v-else class="text-body-2 text-medium-emphasis">#{{ i + 1 }}</span>
            </div>
            <v-avatar size="32" color="primary" variant="tonal" class="mr-3">
              <span class="text-caption font-weight-bold">{{ initials(entry.name) }}</span>
            </v-avatar>
          </template>

          <v-list-item-title class="d-flex align-center ga-2">
            <span class="font-weight-medium">{{ entry.name }}</span>
            <v-chip
              v-if="entry.streak_count > 0"
              size="x-small"
              color="warning"
              variant="tonal"
              prepend-icon="mdi-fire"
            >
              {{ entry.streak_count }}d
            </v-chip>
          </v-list-item-title>

          <v-list-item-subtitle class="d-flex align-center ga-2 mt-1">
            <span class="text-caption">
              {{ LEVEL_ICONS[entry.level_name] || '🌱' }} Lv.{{ entry.level }}
            </span>
            <!-- Mini XP bar -->
            <div class="lb-row__bar">
              <div
                class="lb-row__bar-fill"
                :style="{ width: xpPercent(entry.total_xp) + '%' }"
              />
            </div>
          </v-list-item-subtitle>

          <template #append>
            <span class="text-body-1 font-weight-bold bo-display" style="color: rgb(var(--v-theme-gold));">
              {{ entry.total_xp.toLocaleString() }}
            </span>
          </template>
        </v-list-item>
      </v-list>
    </v-card>
    </div>
      </v-window-item>
    </v-window>
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useXPStore } from '@/stores/xp'
import { useAuthStore } from '@/stores/auth'
import RaceLeaderboardTab from './RaceLeaderboardTab.vue'
import LeaderboardPodium, { type PodiumEntry } from '@/components/leaderboard/LeaderboardPodium.vue'

const activeTab = ref<'xp' | 'race-100' | 'race-200'>('xp')

const xpStore = useXPStore()
const authStore = useAuthStore()
const loading = ref(true)

const MEDALS = ['🥇', '🥈', '🥉']
const LEVEL_ICONS: Record<string, string> = {
  seedling: '🌱', sprout: '🌿', sapling: '🌲', tree: '🌳', ancient_oak: '🏔️',
}

const currentUserId = computed(() => authStore.user?.id || '')

// Deduplicate entries by user_id (backend may return dupes via join)
const entries = computed(() => {
  const seen = new Set<string>()
  return xpStore.leaderboard.filter(e => {
    if (seen.has(e.user_id)) return false
    seen.add(e.user_id)
    return true
  })
})

const maxXP = computed(() => Math.max(1, ...entries.value.map(e => e.total_xp)))

function xpPercent(xp: number): number {
  return (xp / maxXP.value) * 100
}

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) || '?'
}

// Top-3 mapped to the shared podium's shape. XP is the reward figure (gold);
// the level line is the meta.
const podiumEntries = computed<PodiumEntry[]>(() =>
  entries.value.slice(0, 3).map(e => ({
    name: e.name,
    figure: `${e.total_xp.toLocaleString()} XP`,
    figureKind: 'gold',
    meta: `${LEVEL_ICONS[e.level_name] || '🌱'} Lv.${e.level}`,
    isMe: e.user_id === currentUserId.value,
  })),
)

onMounted(async () => {
  await xpStore.fetchLeaderboard()
  loading.value = false
})
</script>

<style scoped>
/* Focused centred column — keeps the board from stretching edge-to-edge on
   wide viewports (which marooned the XP value far to the right). */
.lb-content {
  max-width: 820px;
  margin: 0 auto;
}

/* Podium markup + styles now live in components/leaderboard/LeaderboardPodium.vue
   (shared with the race tabs). */

/* ─── List Rows ───────────────────────── */
.lb-row__rank {
  min-width: 36px;
  text-align: center;
  margin-right: 8px;
}
.lb-row__medal { font-size: 20px; }

.lb-row--me {
  background: rgba(var(--v-theme-primary), 0.08) !important;
  border-left: 3px solid rgb(var(--v-theme-primary));
}

.lb-row__bar {
  flex: 1;
  max-width: 200px;
  height: 5px;
  border-radius: var(--radius-pill, 999px);
  background: rgb(var(--v-theme-rule));
  overflow: hidden;
}
/* Growth → harvest: leaf-green ramps to gold as XP fills. */
.lb-row__bar-fill {
  height: 100%;
  border-radius: var(--radius-pill, 999px);
  background: linear-gradient(90deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-gold)));
  transition: width var(--dur-long, 360ms) var(--ease-out, ease);
}
</style>
