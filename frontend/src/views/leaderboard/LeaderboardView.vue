<template>
  <v-container class="py-6" fluid>
    <div class="d-flex align-center mb-6">
      <v-icon icon="mdi-trophy" color="secondary" size="28" class="mr-2" />
      <div class="text-h5 font-weight-bold">Leaderboard</div>
    </div>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

    <!-- Top 3 Podium -->
    <div v-if="topThree.length > 0" class="podium mb-6">
      <div
        v-for="(entry, i) in topThree"
        :key="entry.user_id"
        class="podium__card"
        :class="{
          'podium__card--gold': i === 0,
          'podium__card--silver': i === 1,
          'podium__card--bronze': i === 2,
          'podium__card--me': entry.user_id === currentUserId,
        }"
      >
        <div class="podium__medal">{{ MEDALS[i] }}</div>
        <v-avatar size="48" color="primary" variant="tonal" class="mb-2">
          <span class="text-body-1 font-weight-bold">
            {{ initials(entry.name) }}
          </span>
        </v-avatar>
        <div class="text-body-2 font-weight-bold text-truncate" style="max-width: 120px;">
          {{ entry.name }}
        </div>
        <div class="podium__level">
          {{ LEVEL_ICONS[entry.level_name] || '⭐' }} Lv.{{ entry.level }}
        </div>
        <div class="text-h6 font-weight-bold" style="color: rgb(var(--v-theme-secondary));">
          {{ entry.total_xp.toLocaleString() }}
          <span class="text-caption">XP</span>
        </div>
        <v-chip
          v-if="entry.streak_count > 0"
          size="x-small"
          color="warning"
          variant="flat"
          prepend-icon="mdi-fire"
        >
          {{ entry.streak_count }}d
        </v-chip>
      </div>
    </div>

    <!-- Rest of leaderboard (4-20) -->
    <v-card v-if="restOfBoard.length > 0" color="surface" class="mb-4">
      <v-list density="compact">
        <v-list-item
          v-for="(entry, i) in restOfBoard"
          :key="entry.user_id"
          :class="{ 'leaderboard__me': entry.user_id === currentUserId }"
        >
          <template #prepend>
            <span class="leaderboard__rank text-body-2 text-medium-emphasis">
              #{{ i + 4 }}
            </span>
          </template>

          <v-list-item-title class="d-flex align-center ga-2">
            <v-avatar size="28" color="primary" variant="tonal">
              <span class="text-caption font-weight-bold">{{ initials(entry.name) }}</span>
            </v-avatar>
            <span class="font-weight-medium">{{ entry.name }}</span>
            <span class="text-caption text-medium-emphasis">
              {{ LEVEL_ICONS[entry.level_name] || '' }} Lv.{{ entry.level }}
            </span>
          </v-list-item-title>

          <template #append>
            <div class="d-flex align-center ga-2">
              <v-chip
                v-if="entry.streak_count > 0"
                size="x-small"
                color="warning"
                variant="tonal"
                prepend-icon="mdi-fire"
              >
                {{ entry.streak_count }}d
              </v-chip>
              <span class="text-body-2 font-weight-bold" style="min-width: 60px; text-align: right;">
                {{ entry.total_xp.toLocaleString() }}
              </span>
            </div>
          </template>
        </v-list-item>
      </v-list>
    </v-card>

    <!-- Empty state -->
    <v-card v-if="!loading && xpStore.leaderboard.length === 0" color="surface" class="pa-8 text-center">
      <v-icon icon="mdi-trophy-outline" size="48" color="medium-emphasis" class="mb-3" />
      <div class="text-body-1 text-medium-emphasis">
        No XP activity yet. Start coding to earn your first points!
      </div>
    </v-card>
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useXPStore } from '@/stores/xp'
import { useAuthStore } from '@/stores/auth'

const xpStore = useXPStore()
const authStore = useAuthStore()
const loading = ref(true)

const MEDALS = ['🥇', '🥈', '🥉']
const LEVEL_ICONS: Record<string, string> = {
  seedling: '🌱', sprout: '🌿', sapling: '🌲', tree: '🌳', ancient_oak: '🏔️',
}

const currentUserId = computed(() => authStore.user?.id || '')

const topThree = computed(() => xpStore.leaderboard.slice(0, 3))
const restOfBoard = computed(() => xpStore.leaderboard.slice(3))

function initials(name: string): string {
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2) || '?'
}

onMounted(async () => {
  await xpStore.fetchLeaderboard()
  loading.value = false
})
</script>

<style scoped>
.podium {
  display: flex;
  justify-content: center;
  gap: 16px;
  flex-wrap: wrap;
}

.podium__card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 24px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
  border: 2px solid rgba(255, 255, 255, 0.08);
  min-width: 160px;
  transition: transform 0.2s;
}

.podium__card:hover {
  transform: translateY(-4px);
}

.podium__card--gold {
  border-color: rgba(255, 215, 0, 0.4);
  background: rgba(255, 215, 0, 0.06);
}
.podium__card--silver {
  border-color: rgba(192, 192, 192, 0.3);
  background: rgba(192, 192, 192, 0.04);
}
.podium__card--bronze {
  border-color: rgba(205, 127, 50, 0.3);
  background: rgba(205, 127, 50, 0.04);
}
.podium__card--me {
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.4);
}

.podium__medal {
  font-size: 32px;
  line-height: 1;
  margin-bottom: 8px;
}

.podium__level {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.6);
  margin: 4px 0;
}

.leaderboard__rank {
  min-width: 32px;
  text-align: center;
}

.leaderboard__me {
  background: rgba(var(--v-theme-primary), 0.08);
  border-left: 3px solid rgb(var(--v-theme-primary));
}
</style>
