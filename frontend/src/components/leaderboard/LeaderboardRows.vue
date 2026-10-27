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

<!-- Everyone below the top three: rank, monogram, name and note, an
     optional progress bar, and the figure. The viewer's row is tinted. -->
<template>
  <section class="lb-rows" :aria-label="label">
    <ol>
      <li v-for="e in entries" :key="e.key" class="lb-rows__row" :class="{ 'lb-rows__row--me': e.isMe }">
        <span class="lb-rows__rank">{{ e.rank }}</span>
        <AppMonogram :name="e.name" />
        <span class="lb-rows__who">
          <span class="lb-rows__name">{{ e.name }}<span v-if="e.isMe" class="lb-rows__you"> (you)</span></span>
          <span v-if="e.note" class="lb-rows__note">{{ e.note }}</span>
        </span>
        <span v-if="e.bar !== undefined" class="lb-rows__bar" aria-hidden="true">
          <span :style="{ width: `${e.bar}%` }" />
        </span>
        <span class="lb-rows__figure">{{ e.figure }}<span v-if="e.unit" class="d-sr-only"> {{ e.unit }}</span></span>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import AppMonogram from '@/components/common/AppMonogram.vue'
import type { RankedEntry } from '@/utils/leaderboard'

defineProps<{ entries: RankedEntry[]; label: string }>()
</script>

<style scoped>
.lb-rows {
  overflow: hidden;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
ol {
  list-style: none;
  margin: 0;
  padding: 0;
}
.lb-rows__row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 20px;
}
.lb-rows__row + .lb-rows__row {
  border-top: 1px solid rgb(var(--v-theme-rule));
}
.lb-rows__row--me {
  background: rgba(var(--v-theme-primary), 0.06);
}
.lb-rows__rank {
  width: 28px;
  flex-shrink: 0;
  font: 600 13px var(--font-mono);
  color: rgb(var(--v-theme-on-surface-variant));
}
.lb-rows__who {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-width: 0;
}
.lb-rows__name {
  font-size: 14px;
  font-weight: 500;
  overflow-wrap: anywhere;
}
.lb-rows__you,
.lb-rows__note {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.lb-rows__bar {
  flex: 0 1 220px;
  height: 6px;
  border-radius: 999px;
  background: rgb(var(--v-theme-surface-variant));
  overflow: hidden;
}
.lb-rows__bar span {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: rgb(var(--v-theme-primary));
}
.lb-rows__figure {
  min-width: 64px;
  text-align: right;
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
@media (max-width: 599.98px) {
  .lb-rows__row {
    gap: 10px;
    padding: 12px 16px;
  }
  .lb-rows__bar {
    display: none;
  }
}
</style>
