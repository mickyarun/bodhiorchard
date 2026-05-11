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
      <div class="text-h5 font-weight-bold">Leaderboard</div>
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
      <v-tab value="race-100">Race 100 m</v-tab>
      <v-tab value="race-200">Race 200 m</v-tab>
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

    <!-- Podium — top 3 with staggered height -->
    <div v-if="entries.length >= 3" class="podium mb-8">
      <!-- 2nd place (left, shorter) -->
      <div class="podium__slot podium__slot--silver">
        <PodiumCard :entry="entries[1]" :rank="2" :is-me="entries[1].user_id === currentUserId" />
      </div>
      <!-- 1st place (center, tallest) -->
      <div class="podium__slot podium__slot--gold">
        <PodiumCard :entry="entries[0]" :rank="1" :is-me="entries[0].user_id === currentUserId" />
      </div>
      <!-- 3rd place (right, shortest) -->
      <div class="podium__slot podium__slot--bronze">
        <PodiumCard :entry="entries[2]" :rank="3" :is-me="entries[2].user_id === currentUserId" />
      </div>
    </div>

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
            <span class="text-body-1 font-weight-bold" style="color: rgb(var(--v-theme-secondary));">
              {{ entry.total_xp.toLocaleString() }}
            </span>
          </template>
        </v-list-item>
      </v-list>
    </v-card>
      </v-window-item>
    </v-window>
  </v-container>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import type { LeaderboardEntry } from '@/types'
import { useXPStore } from '@/stores/xp'
import { useAuthStore } from '@/stores/auth'
import RaceLeaderboardTab from './RaceLeaderboardTab.vue'

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

onMounted(async () => {
  await xpStore.fetchLeaderboard()
  loading.value = false
})

// Inline PodiumCard component (small, only used here)
const PodiumCard = defineComponent({
  props: {
    entry: { type: Object as () => LeaderboardEntry, required: true },
    rank: { type: Number, required: true },
    isMe: { type: Boolean, default: false },
  },
  setup(props) {
    return () => h('div', {
      class: ['podium-card', props.isMe && 'podium-card--me'],
    }, [
      h('div', { class: 'podium-card__medal' }, MEDALS[props.rank - 1]),
      h('div', { class: 'podium-card__name text-body-2 font-weight-bold' }, props.entry.name),
      h('div', { class: 'podium-card__level text-caption' },
        `${LEVEL_ICONS[props.entry.level_name] || '🌱'} Lv.${props.entry.level}`),
      h('div', {
        class: 'podium-card__xp text-h6 font-weight-bold',
        style: 'color: rgb(var(--v-theme-secondary))',
      }, `${props.entry.total_xp.toLocaleString()} XP`),
    ])
  },
})
</script>

<style scoped>
/* ─── Podium ──────────────────────────── */
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

.podium-card--me {
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.4);
}

.podium__slot--gold .podium-card {
  border-color: rgba(255, 215, 0, 0.35);
  background: rgba(255, 215, 0, 0.05);
  padding: 24px 32px;
  min-width: 180px;
}
.podium__slot--silver .podium-card {
  border-color: rgba(192, 192, 192, 0.25);
  background: rgba(192, 192, 192, 0.04);
}
.podium__slot--bronze .podium-card {
  border-color: rgba(205, 127, 50, 0.25);
  background: rgba(205, 127, 50, 0.04);
}

.podium-card__medal { font-size: 36px; line-height: 1; }
.podium-card__level { color: rgba(255, 255, 255, 0.5); }

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
  max-width: 120px;
  height: 4px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}
.lb-row__bar-fill {
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-secondary)));
  transition: width 0.4s ease;
}
</style>
