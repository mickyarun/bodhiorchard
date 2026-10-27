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

<!-- The top three as cards in rank order. First place carries the gold
     reward colour on its rank and border. -->
<template>
  <ol class="podium" aria-label="Top three">
    <li v-for="e in entries" :key="e.key" class="podium__card" :class="{ 'podium__card--first': e.rank === 1, 'podium__card--me': e.isMe }">
      <span class="podium__rank">{{ ordinal(e.rank) }}</span>
      <AppMonogram :name="e.name" :size="xs ? 40 : 56" />
      <span class="podium__name">{{ e.name }}<span v-if="e.isMe" class="podium__you"> (you)</span></span>
      <span class="podium__figure">{{ e.figure }} <span v-if="e.unit" class="podium__unit">{{ e.unit }}</span></span>
      <span v-if="e.note" class="podium__note">{{ e.note }}</span>
    </li>
  </ol>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import AppMonogram from '@/components/common/AppMonogram.vue'
import { ordinal, type RankedEntry } from '@/utils/leaderboard'

defineProps<{ entries: RankedEntry[] }>()

// Phones stack the cards into rows with a smaller monogram.
const { xs } = useDisplay()
</script>

<style scoped>
.podium {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.podium__card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 22px;
  text-align: center;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
.podium__card--first {
  border-color: rgba(var(--v-theme-gold), 0.6);
}
.podium__card--me {
  background: rgba(var(--v-theme-primary), 0.05);
}
.podium__rank {
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface-variant));
}
.podium__card--first .podium__rank {
  color: rgb(var(--v-theme-gold));
}
.podium__name {
  max-width: 100%;
  font-size: 16px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.podium__you,
.podium__unit,
.podium__note {
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface-variant));
}
.podium__figure {
  font-size: 26px;
  font-weight: 600;
  letter-spacing: var(--tracking-display);
  font-variant-numeric: tabular-nums;
}
@media (max-width: 599.98px) {
  .podium {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }
  .podium__card {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 4px 12px;
    padding: 14px 16px;
    text-align: left;
  }
  .podium__rank {
    width: 28px;
  }
  .podium__name {
    flex: 1 1 0;
    min-width: 0;
  }
  .podium__figure {
    font-size: 20px;
  }
  .podium__note {
    flex-basis: 100%;
    padding-left: 80px;
  }
}
</style>
