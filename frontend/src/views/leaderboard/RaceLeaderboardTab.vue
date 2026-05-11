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
      No race results yet at {{ distance }} m. Invite a colleague from the garden to start one!
    </div>

    <template v-else>
      <!-- Podium -->
      <div v-if="entries.length >= 3" class="podium mb-6">
        <div class="podium__slot podium__slot--silver">
          <PodiumCard :row="entries[1]" :rank="2" />
        </div>
        <div class="podium__slot podium__slot--gold">
          <PodiumCard :row="entries[0]" :rank="1" />
        </div>
        <div class="podium__slot podium__slot--bronze">
          <PodiumCard :row="entries[2]" :rank="3" />
        </div>
      </div>

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
              {{ formatRaceTime(row.finishTimeMs ?? 0) }} · {{ row.distanceM }} m · {{ relativeDate(row.finishedAt) }}
            </v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, watch } from 'vue'
import { useRaceLeaderboardStore, type RaceLeaderboardRow } from '@/stores/raceLeaderboard'
import { formatRaceTime } from '@/engine/race/formatTime'

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

const PodiumCard = defineComponent({
  props: {
    row: { type: Object as () => RaceLeaderboardRow, required: true },
    rank: { type: Number, required: true },
  },
  setup(props) {
    return () => h('div', { class: 'podium-card' }, [
      h('div', { class: 'podium-card__medal' }, MEDALS[props.rank - 1]),
      h('div', { class: 'podium-card__name text-body-2 font-weight-bold' }, props.row.userName),
      h('div', { class: 'podium-card__time text-h6 font-weight-bold' },
        formatRaceTime(props.row.finishTimeMs ?? 0)),
      h('div', { class: 'podium-card__distance text-caption text-medium-emphasis' },
        `${props.row.distanceM} m`),
    ])
  },
})
</script>

<style scoped>
.podium {
  display: flex;
  justify-content: center;
  align-items: flex-end;
  gap: 12px;
}
.podium__slot { display: flex; justify-content: center; }
.podium__slot--gold { align-self: flex-start; }
.podium__slot--silver { align-self: center; }
.podium__slot--bronze { align-self: flex-end; }

.podium-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 28px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
  border: 2px solid rgba(255, 255, 255, 0.08);
  min-width: 160px;
  gap: 6px;
}
.podium__slot--gold .podium-card {
  border-color: rgba(255, 215, 0, 0.35);
  background: rgba(255, 215, 0, 0.05);
  min-width: 180px;
}
.podium-card__medal { font-size: 36px; line-height: 1; }

.lb-row__rank { min-width: 36px; text-align: center; margin-right: 8px; }
.lb-row__medal { font-size: 20px; }
</style>
