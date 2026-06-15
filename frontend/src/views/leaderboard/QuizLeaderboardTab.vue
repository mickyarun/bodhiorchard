<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->
<!-- Monthly quiz standings — champion banner + chasers. Top scorer earns SP. -->
<script setup lang="ts">
import { computed, onMounted } from 'vue'

import AppCallout from '@/components/common/AppCallout.vue'
import { useAuthStore } from '@/stores/auth'
import { useQuizStore } from '@/stores/quiz'

const store = useQuizStore()
const authStore = useAuthStore()
const myId = computed(() => authStore.user?.id)

// A 0-point top scorer isn't a champion — someone has to actually score to lead.
const hasLeader = computed(() => (store.monthly[0]?.totalPoints ?? 0) > 0)
const leader = computed(() => (hasLeader.value ? store.monthly[0] : null))
const chasers = computed(() => (hasLeader.value ? store.monthly.slice(1) : []))

function medal(rank: number): string {
  return ['🥈', '🥉'][rank] ?? `#${rank + 2}`
}

onMounted(() => store.fetchMonthly())
</script>

<template>
  <div>
    <AppCallout
      variant="info"
      eyebrow="Monthly prize"
      icon="mdi-trophy-variant-outline"
      class="mb-5"
    >
      The top scorer this month earns <strong>SP</strong> — a rare reward. No XP is awarded
      for the quiz.
    </AppCallout>

    <div v-if="!hasLeader" class="quiz-empty">
      <v-icon size="48" color="medium-emphasis">mdi-podium-gold</v-icon>
      <p class="text-h6 mt-3 mb-1">No points on the board yet</p>
      <p class="text-medium-emphasis mb-0">
        Answer a quiz correctly to take the top spot this month.
      </p>
    </div>

    <template v-else>
      <!-- Champion -->
      <div class="champion" :class="{ 'champion--me': leader && leader.userId === myId }">
        <div class="champion__crown">👑</div>
        <div class="champion__body">
          <div class="champion__eyebrow">Leading this month</div>
          <div class="champion__name">{{ leader?.userName }}</div>
          <div class="champion__meta">{{ leader?.correctCount }} correct</div>
        </div>
        <div class="champion__score">
          <span class="champion__pts">{{ leader?.totalPoints }}</span>
          <span class="champion__lbl">pts</span>
        </div>
      </div>

      <!-- Chasers -->
      <div v-if="chasers.length" class="chasers">
        <div
          v-for="(e, i) in chasers"
          :key="e.userId"
          class="row"
          :class="{ 'row--me': e.userId === myId }"
        >
          <span class="row__rank">{{ medal(i) }}</span>
          <span class="row__name">
            {{ e.userName }}
            <v-chip v-if="e.userId === myId" size="x-small" color="primary" variant="tonal">
              you
            </v-chip>
          </span>
          <span class="row__correct">{{ e.correctCount }} ✓</span>
          <span class="row__pts">{{ e.totalPoints }}</span>
        </div>
      </div>
      <p v-else class="text-medium-emphasis text-center mt-4 mb-0">
        No challengers yet — will anyone catch up?
      </p>
    </template>
  </div>
</template>

<style scoped>
.quiz-empty {
  text-align: center;
  padding: var(--space-xl) 0;
}

.champion {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  border-radius: var(--radius-card);
  border: 1px solid color-mix(in oklch, var(--color-gold) 45%, var(--color-rule));
  background:
    radial-gradient(140% 120% at 100% 0%, color-mix(in oklch, var(--color-gold) 16%, transparent),
      transparent 60%),
    var(--color-paper-2);
  margin-bottom: var(--space-md);
}
.champion--me {
  border-color: var(--color-gold);
}
.champion__crown {
  font-size: 2.25rem;
  line-height: 1;
}
.champion__body {
  flex: 1 1 auto;
  min-width: 0;
}
.champion__eyebrow {
  font-size: var(--text-xs);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-gold);
}
.champion__name {
  font-size: var(--text-md);
  font-weight: 700;
  color: var(--color-ink);
}
.champion__meta {
  font-size: var(--text-sm);
  color: var(--color-muted);
}
.champion__score {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.champion__pts {
  font-size: var(--text-lg);
  font-weight: 800;
  color: var(--color-gold);
  font-variant-numeric: tabular-nums;
}
.champion__lbl {
  font-size: var(--text-sm);
  color: var(--color-muted);
}

.chasers {
  display: flex;
  flex-direction: column;
}
.row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-sm);
  border-radius: var(--radius-input);
  transition: background var(--dur-short) var(--ease-out);
}
.row:hover {
  background: var(--color-paper-2);
}
.row--me {
  background: var(--color-paper-3);
}
.row__rank {
  min-width: 2rem;
  font-weight: 700;
  color: var(--color-muted);
  font-variant-numeric: tabular-nums;
}
.row__name {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2xs);
}
.row__correct {
  color: var(--color-muted);
  font-size: var(--text-sm);
}
.row__pts {
  min-width: 3rem;
  text-align: right;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
</style>
