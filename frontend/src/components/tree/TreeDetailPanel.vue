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
  <v-card class="tree-detail-panel" elevation="8" rounded="lg">
    <!-- Header -->
    <div class="d-flex align-center px-4 pt-3 pb-1">
      <v-icon icon="mdi-pine-tree" color="green" class="mr-2" />
      <span class="text-subtitle-1 font-weight-bold text-truncate">
        {{ repo.repo_name }}
      </span>
      <v-spacer />
      <v-btn
        icon="mdi-close"
        size="x-small"
        variant="text"
        @click="emit('close')"
      />
    </div>

    <div class="d-flex align-center ga-1 px-4 pb-2">
      <v-chip :color="healthColor" size="x-small" variant="tonal">
        {{ repo.health }}
      </v-chip>
      <v-chip size="x-small" variant="outlined">
        {{ repo.growth_stage }}
      </v-chip>
      <span class="text-caption text-medium-emphasis ml-1">
        {{ repo.total_files }} files
      </span>
    </div>

    <v-divider />

    <!-- Scrollable content -->
    <div class="tree-detail-panel__content">
      <!-- Latest Released -->
      <div class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">
          Latest Released
        </div>
        <template v-if="latestReleased.length > 0">
          <div
            v-for="f in latestReleased"
            :key="f.title"
            class="d-flex align-center ga-2 py-1"
          >
            <v-icon icon="mdi-fruit-cherries" size="16" color="orange" />
            <span class="text-body-2 text-truncate">{{ f.title }}</span>
          </div>
        </template>
        <div v-else class="text-body-2 text-disabled">
          No released features yet
        </div>
      </div>

      <v-divider />

      <!-- Active Branches -->
      <div class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">
          Active Branches ({{ activeBranches.length }})
        </div>
        <div class="d-flex flex-wrap ga-1">
          <v-chip
            v-for="b in activeBranches"
            :key="b.name"
            size="small"
            variant="tonal"
            :color="branchColor(b.health)"
          >
            {{ b.name }}
            <span class="text-caption ml-1 opacity-70">
              {{ b.file_count }}
            </span>
          </v-chip>
        </div>
        <div v-if="activeBranches.length === 0" class="text-body-2 text-disabled">
          No active branches
        </div>
      </div>

      <v-divider />

      <!-- All Features -->
      <div class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">
          Features ({{ repoFeatures.length }})
        </div>
        <div
          v-for="f in repoFeatures"
          :key="f.title"
          class="d-flex align-center ga-2 py-1"
        >
          <v-icon
            :icon="statusIcon(f.status)"
            :color="statusColor(f.status)"
            size="16"
          />
          <span class="text-body-2 text-truncate flex-grow-1">
            {{ f.title }}
          </span>
          <v-chip
            :color="statusColor(f.status)"
            size="x-small"
            variant="tonal"
            class="flex-shrink-0"
          >
            {{ f.status }}
          </v-chip>
        </div>
        <div v-if="repoFeatures.length === 0" class="text-body-2 text-disabled">
          No features registered
        </div>
      </div>

      <v-divider />

      <!-- Developers -->
      <div class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">
          Developers ({{ developers.length }})
        </div>
        <div
          v-for="m in developers"
          :key="m.user_id"
          class="d-flex align-center ga-2 py-1"
        >
          <v-avatar size="24" color="purple-lighten-4">
            <v-img v-if="m.avatar_url" :src="m.avatar_url" />
            <v-icon v-else icon="mdi-account" size="16" />
          </v-avatar>
          <div class="flex-grow-1 overflow-hidden">
            <div class="text-body-2 text-truncate">{{ m.name }}</div>
            <div class="text-caption text-medium-emphasis text-truncate">
              {{ m.top_modules.join(', ') }} · {{ m.care_pct }}%
            </div>
          </div>
        </div>
        <div v-if="developers.length === 0" class="text-body-2 text-disabled">
          No developers matched
        </div>
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type {
  RepoLimbData,
  FeatureItem,
  MemberActivity,
} from '@/types/dashboard'

const props = defineProps<{
  repo: RepoLimbData
  features: FeatureItem[]
  developers: MemberActivity[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const healthColor = computed(() => {
  const map: Record<string, string> = {
    thriving: 'green',
    healthy: 'blue',
    dormant: 'grey',
    wilted: 'brown',
  }
  return map[props.repo.health] ?? 'grey'
})

const latestReleased = computed(() =>
  props.features
    .filter(f => f.status === 'implemented' || f.status === 'released')
    .slice(0, 3),
)

const activeBranches = computed(() =>
  props.repo.branches.filter(
    b => b.health !== 'dormant' || b.commit_count > 0,
  ),
)

const repoFeatures = computed(() => props.features)

function branchColor(health: string): string {
  const map: Record<string, string> = {
    thriving: 'green',
    healthy: 'blue',
    dormant: 'grey',
    wilted: 'brown',
  }
  return map[health] ?? 'grey'
}

function statusIcon(status: string): string {
  const map: Record<string, string> = {
    implemented: 'mdi-check-circle',
    released: 'mdi-check-circle',
    in_progress: 'mdi-progress-wrench',
    planned: 'mdi-calendar-outline',
  }
  return map[status] ?? 'mdi-circle-outline'
}

function statusColor(status: string): string {
  const map: Record<string, string> = {
    implemented: 'success',
    released: 'success',
    in_progress: 'warning',
    planned: 'info',
  }
  return map[status] ?? 'grey'
}
</script>

<style scoped>
.tree-detail-panel {
  position: absolute;
  top: 8px;
  right: 8px;
  bottom: 8px;
  width: 320px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  background: rgba(var(--v-theme-surface), 0.95) !important;
  backdrop-filter: blur(8px);
}

.tree-detail-panel__content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
