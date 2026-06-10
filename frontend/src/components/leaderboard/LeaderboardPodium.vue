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

<!-- Shared top-3 podium for the XP and Race leaderboards. Owns the staggered
     slot layout (2nd left, 1st centre + harvest-gold glow, 3rd right) and the
     card styling so the two tabs cannot drift apart. Callers map their rows to
     `PodiumEntry[]` (rank order: index 0 is first place). -->
<template>
  <div class="podium">
    <div
      v-for="slot in slots"
      :key="slot.rank"
      class="podium__slot"
      :class="`podium__slot--${slot.tier}`"
    >
      <div class="podium-card" :class="{ 'podium-card--me': slot.entry.isMe }">
        <div class="podium-card__medal">{{ MEDALS[slot.rank - 1] }}</div>
        <div class="podium-card__name text-body-2 font-weight-bold">{{ slot.entry.name }}</div>
        <div
          class="podium-card__figure bo-display text-h6 font-weight-bold"
          :class="`podium-card__figure--${slot.entry.figureKind}`"
        >
          {{ slot.entry.figure }}
        </div>
        <div v-if="slot.entry.meta" class="podium-card__meta text-caption text-medium-emphasis">
          {{ slot.entry.meta }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export interface PodiumEntry {
  name: string
  // The headline number for this board — XP total or finish time.
  figure: string
  // 'gold' tints the figure with the reward signal (XP); 'ink' keeps it a
  // neutral metric (a finish time isn't a reward).
  figureKind: 'gold' | 'ink'
  // Optional small line under the figure (level, distance, …).
  meta?: string
  isMe?: boolean
}

const props = defineProps<{
  // Top three in rank order — index 0 is first place.
  entries: PodiumEntry[]
}>()

const MEDALS = ['🥇', '🥈', '🥉']

// Visual order: silver (2nd) left, gold (1st) centre, bronze (3rd) right.
const slots = computed(() =>
  [
    { rank: 2, tier: 'silver', entry: props.entries[1] },
    { rank: 1, tier: 'gold', entry: props.entries[0] },
    { rank: 3, tier: 'bronze', entry: props.entries[2] },
  ].filter((s) => s.entry),
)
</script>

<style scoped>
.podium {
  display: flex;
  justify-content: center;
  align-items: flex-end;
  gap: 12px;
}

.podium__slot {
  display: flex;
  justify-content: center;
}
.podium__slot--gold {
  align-self: flex-start;
}
.podium__slot--silver {
  align-self: center;
}
.podium__slot--bronze {
  align-self: flex-end;
}

.podium-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 28px;
  border-radius: 16px;
  background: rgb(var(--v-theme-surface-bright));
  border: 1px solid rgb(var(--v-theme-rule));
  min-width: 160px;
  gap: 6px;
}

.podium-card--me {
  box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), 0.4);
}

/* 1st place is the harvest moment — the reserved gold signal + soft glow.
   Silver / bronze keep their universally-read medal tints. */
.podium__slot--gold .podium-card {
  border-color: rgba(var(--v-theme-gold), 0.5);
  background: rgba(var(--v-theme-gold), 0.08);
  box-shadow: 0 0 24px rgba(var(--v-theme-gold), 0.18);
  padding: 24px 32px;
  min-width: 180px;
}
.podium__slot--silver .podium-card {
  border-color: rgba(192, 192, 192, 0.3);
  background: rgba(192, 192, 192, 0.05);
}
.podium__slot--bronze .podium-card {
  border-color: rgba(205, 127, 50, 0.3);
  background: rgba(205, 127, 50, 0.05);
}

.podium-card__medal {
  font-size: 36px;
  line-height: 1;
}
.podium-card__figure {
  font-variant-numeric: tabular-nums;
}
.podium-card__figure--gold {
  color: rgb(var(--v-theme-gold));
}
.podium-card__figure--ink {
  color: rgb(var(--v-theme-on-surface));
}
.podium-card__meta {
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
