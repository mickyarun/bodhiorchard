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

<!-- Best circuit times at one distance, fastest first, with when each was set. -->
<template>
  <LeaderboardBoard
    :entries="entries"
    :label="`Circuit times, ${lapLabel(distance)}`"
    :empty-text="`No circuit times yet at ${lapLabel(distance)}. Race a colleague in the dashboard's 3D view to set the first one.`"
    :loading="loading"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import LeaderboardBoard from '@/components/leaderboard/LeaderboardBoard.vue'
import { useNow } from '@/composables/useNow'
import { formatRaceTime } from '@/engine/race/formatTime'
import { useAuthStore } from '@/stores/auth'
import { useRaceLeaderboardStore } from '@/stores/raceLeaderboard'
import { relativeTime } from '@/utils/date'
import type { BoardEntry } from '@/utils/leaderboard'
import { lapLabel } from '@shared/race/RaceConstants'

const props = defineProps<{ distance: 100 | 200 }>()

const store = useRaceLeaderboardStore()
const authStore = useAuthStore()
const now = useNow()

const rows = computed(() => (props.distance === 100 ? store.entries100 : store.entries200))
const loading = computed(() => (props.distance === 100 ? store.loading100 : store.loading200))

const entries = computed<BoardEntry[]>(() =>
  rows.value.map((row, i) => ({
    key: `${row.userId}:${row.finishedAt}:${i}`,
    name: row.userName,
    figure: formatRaceTime(row.finishTimeMs ?? 0),
    note: relativeTime(row.finishedAt, now.value),
    isMe: row.userId === authStore.user?.id,
  })),
)

watch(() => props.distance, d => void store.fetchLeaderboard(d))
onMounted(() => void store.fetchLeaderboard(props.distance))
</script>
