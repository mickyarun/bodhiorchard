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

<!-- One board: the top three as cards and everyone else in a ranked list,
     a loading spinner the first time, or a plain empty message. -->
<template>
  <div class="lb-board">
    <div v-if="loading && !entries.length" class="lb-board__loading">
      <v-progress-circular indeterminate color="primary" :aria-label="`Loading ${label}`" />
    </div>
    <p v-else-if="!entries.length" class="lb-board__empty">{{ emptyText }}</p>
    <template v-else>
      <LeaderboardPodium v-if="split.podium.length" :entries="split.podium" />
      <LeaderboardRows v-if="split.rest.length" :entries="split.rest" :label="label" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { splitPodium, type BoardEntry } from '@/utils/leaderboard'
import LeaderboardPodium from './LeaderboardPodium.vue'
import LeaderboardRows from './LeaderboardRows.vue'

const props = defineProps<{ entries: BoardEntry[]; label: string; emptyText: string; loading?: boolean }>()

const split = computed(() => splitPodium(props.entries))
</script>

<style scoped>
.lb-board {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.lb-board__loading {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}
.lb-board__empty {
  margin: 0;
  padding: 48px 16px;
  text-align: center;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
</style>
