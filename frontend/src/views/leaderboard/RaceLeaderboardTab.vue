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
      No circuit results yet at {{ lapLabel(distance) }}. Invite a colleague from the garden to start one!
    </div>

    <template v-else>
      <div class="lb-content">
      <!-- Podium — shared with the XP tab. -->
      <LeaderboardPodium v-if="entries.length >= 3" :entries="podiumEntries" class="mb-6" />

      <!-- Full ranked list -->
      <v-card color="surface">
        <v-list density="comfortable" class="bg-transparent">
          <v-list-item
            v-for="(row, i) in entries"
            :key="`${row.userId}:${row.distanceM}:${row.finishedAt}`"
          >
            <template #prepend>
              <div class="lb-row__rank">
                <span v-if="i < 3" class="lb-row__medal">{{ MEDALS[i] }}</span>
                <span v-else class="text-body-2 text-medium-emphasis">#{{ i + 1 }}</span>
              </div>
              <v-avatar size="32" color="primary" variant="tonal" class="mr-3">
                <span class="text-caption font-weight-bold">{{ initials(row.userName) }}</span>
              </v-avatar>
            </template>
            <v-list-item-title class="font-weight-medium">
              {{ row.userName }}
            </v-list-item-title>
            <v-list-item-subtitle class="text-caption">
              {{ lapLabel(row.distanceM) }} · {{ relativeDate(row.finishedAt) }}
            </v-list-item-subtitle>
            <template #append>
              <span class="bo-display font-weight-bold race-time">
                {{ formatRaceTime(row.finishTimeMs ?? 0) }}
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
import { computed, onMounted, watch } from 'vue'
import { useRaceLeaderboardStore } from '@/stores/raceLeaderboard'
import { formatRaceTime } from '@/engine/race/formatTime'
import { lapLabel } from '@shared/race/RaceConstants'
import LeaderboardPodium, { type PodiumEntry } from '@/components/leaderboard/LeaderboardPodium.vue'

const props = defineProps<{
  distance: 100 | 200
}>()

const store = useRaceLeaderboardStore()

const entries = computed(() =>
  props.distance === 100 ? store.entries100 : store.entries200,
)

const loading = computed(() =>
  props.distance === 100 ? store.loading100 : store.loading200,
)

const MEDALS = ['\ud83e\udd47', '\ud83e\udd48', '\ud83e\udd49']

watch(
  () => props.distance,
  (d) => { void store.fetchLeaderboard(d) },
  { immediate: false },
)

onMounted(() => {
  void store.fetchLeaderboard(props.distance)
})

function initials(name: string): string {
  if (!name) return '?'
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) || '?'
}

function relativeDate(iso: string): string {
  if (!iso) return ''
  const then = Date.parse(iso)
  if (!Number.isFinite(then)) return ''
  const diffMs = Date.now() - then
  const day = 24 * 60 * 60 * 1000
  if (diffMs < day) return 'today'
  const days = Math.floor(diffMs / day)
  return days === 1 ? 'yesterday' : `${days} days ago`
}

// Top-3 mapped to the shared podium. The finish time is a neutral metric
// (not a reward), so it uses the 'ink' figure kind; distance is the meta.
const podiumEntries = computed<PodiumEntry[]>(() =>
  entries.value.slice(0, 3).map(row => ({
    name: row.userName,
    figure: formatRaceTime(row.finishTimeMs ?? 0),
    figureKind: 'ink',
    meta: `${row.distanceM} m`,
  })),
)
</script>

<style scoped>
/* Focused centred column — matches the XP tab so race results don't
   stretch edge-to-edge with the finish time marooned on the far right. */
.lb-content {
  max-width: 820px;
  margin: 0 auto;
}

.race-time {
  color: rgb(var(--v-theme-on-surface));
  font-size: 1.05rem;
  font-variant-numeric: tabular-nums;
}

/* Podium markup + styles live in components/leaderboard/LeaderboardPodium.vue. */

.lb-row__rank { min-width: 36px; text-align: center; margin-right: 8px; }
.lb-row__medal { font-size: 20px; }
</style>
