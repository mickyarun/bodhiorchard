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
  <section class="lb" aria-label="Org top times">
    <header class="lb__header">
      <span class="lb__eyebrow">org top times</span>
      <h2 class="lb__title">Best {{ distanceM }} m runs</h2>
    </header>

    <div v-if="loading" class="lb__state">
      <v-progress-circular indeterminate size="20" width="2" />
      <span>Loading leaderboard…</span>
    </div>
    <div v-else-if="error" class="lb__state lb__state--error">{{ error }}</div>
    <div v-else-if="!visibleEntries.length" class="lb__state">
      No finishes yet — be the first.
    </div>
    <ol v-else class="lb__list">
      <li
        v-for="(row, idx) in visibleEntries"
        :key="row.userId"
        :class="['lb__row', { 'lb__row--you': row.userId === currentUserId }]"
      >
        <span class="lb__rank">{{ idx + 1 }}</span>
        <span class="lb__name">{{ row.userName || 'Unknown racer' }}</span>
        <span class="lb__time">{{ formatRaceTime(row.finishTimeMs ?? 0) }}</span>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useRaceLeaderboardStore } from '@/stores/raceLeaderboard'
import { useAuthStore } from '@/stores/auth'
import { formatRaceTime } from '@/engine/race/formatTime'

const props = withDefaults(
  defineProps<{
    distanceM: 100 | 200
    limit?: number
  }>(),
  { limit: 10 },
)

const store = useRaceLeaderboardStore()
const { entries100, entries200, loading100, loading200, error } = storeToRefs(store)
const authStore = useAuthStore()

const currentUserId = computed(() => authStore.user?.id ?? '')

// Pick the distance-specific slice so a stale 100 m fetch doesn't bleed
// into a 200 m race result view.
const entries = computed(() =>
  props.distanceM === 100 ? entries100.value : entries200.value,
)
const loading = computed(() =>
  props.distanceM === 100 ? loading100.value : loading200.value,
)
const visibleEntries = computed(() => entries.value.slice(0, props.limit))

onMounted(() => {
  // Server already dedupes per user, but the store cache may hold a
  // larger limit from a previous /leaderboard page visit — refetch to
  // ensure the result just persisted is reflected.
  void store.fetchLeaderboard(props.distanceM, props.limit)
})
</script>

<style scoped>
.lb {
  margin-top: 24px;
  padding: 18px 20px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  background: rgba(0, 0, 0, 0.28);
  backdrop-filter: blur(6px);
}

.lb__header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.lb__eyebrow {
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #ffd75e;
}

.lb__title {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  color: #fff;
}

.lb__state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 4px;
  color: rgba(255, 255, 255, 0.6);
  font-size: 13px;
}

.lb__state--error {
  color: #ff8a73;
}

.lb__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.lb__row {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.88);
  font-size: 13px;
}

.lb__row--you {
  background: rgba(255, 215, 94, 0.12);
  outline: 1px solid rgba(255, 215, 94, 0.32);
  color: #fff;
}

.lb__rank {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.5);
  text-align: right;
}

.lb__row--you .lb__rank {
  color: #ffd75e;
}

.lb__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.lb__time {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
}
</style>
