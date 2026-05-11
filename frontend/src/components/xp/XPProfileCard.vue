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
  <v-card color="surface" class="xp-profile-card pa-4" :class="{ 'xp-profile-card--glow': nearLevelUp }">
    <div class="d-flex align-center ga-3 mb-3">
      <!-- Level badge -->
      <div class="d-flex align-center ga-1">
        <span class="xp-profile-card__icon">{{ levelIcon }}</span>
        <span class="text-body-2 font-weight-bold">Lv.{{ level }}</span>
        <span class="text-caption text-medium-emphasis text-capitalize">
          {{ levelName.replace('_', ' ') }}
        </span>
      </div>

      <v-spacer />

      <!-- Skill Points -->
      <v-chip
        v-if="skillPoints !== undefined"
        variant="tonal"
        color="primary"
        size="small"
      >
        <v-icon start size="14">mdi-star-four-points</v-icon>
        {{ formatSP(skillPoints) }} SP
      </v-chip>

      <!-- Total XP -->
      <span class="text-h6 font-weight-bold" style="color: rgb(var(--v-theme-secondary));">
        {{ totalXp.toLocaleString() }}
        <span class="text-caption font-weight-medium text-medium-emphasis">XP</span>
      </span>

      <!-- Streak -->
      <v-chip
        v-if="streakCount > 0"
        :color="streakCount >= 7 ? 'error' : 'warning'"
        variant="flat"
        size="small"
        :class="{ 'streak-pulse': streakCount >= 7 }"
      >
        <v-icon start :icon="streakCount >= 7 ? 'mdi-fire-alert' : 'mdi-fire'" />
        {{ streakCount }}d
      </v-chip>
    </div>

    <!-- Progress bar -->
    <div class="xp-profile-card__bar">
      <div
        class="xp-profile-card__bar-fill"
        :style="{ width: progress + '%' }"
      />
    </div>

    <!-- Next level text -->
    <div v-if="xpToNextLevel > 0" class="text-caption text-medium-emphasis mt-2">
      {{ xpToNextLevel.toLocaleString() }} XP to
      <span class="text-capitalize font-weight-medium" style="color: rgb(var(--v-theme-secondary));">
        {{ nextLevelDisplay }}
      </span>
    </div>
    <div v-else class="text-caption mt-2" style="color: rgb(var(--v-theme-secondary));">
      Max level reached!
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatSP } from '@/utils/format'

const props = defineProps<{
  totalXp: number
  level: number
  levelName: string
  xpToNextLevel: number
  nextLevelThreshold: number
  streakCount: number
  skillPoints?: number
}>()

const LEVEL_ICONS: Record<string, string> = {
  seedling: '🌱', sprout: '🌿', sapling: '🌲', tree: '🌳', ancient_oak: '🏔️',
}
const LEVEL_NAMES = ['seedling', 'sprout', 'sapling', 'tree', 'ancient_oak']

const levelIcon = computed(() => LEVEL_ICONS[props.levelName] || '⭐')

const progress = computed(() => {
  if (props.nextLevelThreshold === 0) return 100
  const into = props.nextLevelThreshold - props.xpToNextLevel
  return Math.min(100, (into / props.nextLevelThreshold) * 100)
})

const nearLevelUp = computed(() => {
  if (props.nextLevelThreshold === 0) return false
  return (props.xpToNextLevel / props.nextLevelThreshold) < 0.2
})

const nextLevelDisplay = computed(() => {
  const idx = LEVEL_NAMES.indexOf(props.levelName)
  if (idx >= 0 && idx < LEVEL_NAMES.length - 1) {
    return LEVEL_NAMES[idx + 1].replace('_', ' ')
  }
  return ''
})
</script>

<style scoped>
.xp-profile-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.3s, box-shadow 0.3s;
}

.xp-profile-card--glow {
  border-color: rgba(var(--v-theme-secondary), 0.4);
  box-shadow: 0 0 16px rgba(var(--v-theme-secondary), 0.15);
}

.xp-profile-card__icon {
  font-size: 22px;
  line-height: 1;
}

.xp-profile-card__bar {
  height: 10px;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.xp-profile-card__bar-fill {
  height: 100%;
  border-radius: 5px;
  background: linear-gradient(90deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-secondary)));
  transition: width 0.6s ease;
}

.streak-pulse {
  animation: pulse-flame 1.5s ease-in-out infinite;
}

@keyframes pulse-flame {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}
</style>
