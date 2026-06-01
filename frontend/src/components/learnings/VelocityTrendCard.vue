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

<!--
  Average cycle days per week of closures. Bars are anchored to a
  hairline base axis so the chart reads as "an axis with N marks"
  even when N=1, avoiding the lonely-sliver-of-bar look the original
  drop suffered from. Tooltip on each bar surfaces the underlying
  week_start + avg_cycle_days + BUD count for that bucket.
-->

<template>
  <section class="card">
    <header class="card__head">
      <v-icon icon="mdi-finance" size="18" color="primary" />
      <div class="card__title">Velocity trend</div>
      <div class="card__sub">
        Average cycle days per week of closures. Bar height is
        relative to the busiest week in this 12-week window.
      </div>
    </header>
    <div v-if="points.length === 0" class="empty-row">
      No closures recorded in the last 12 weeks.
    </div>
    <div v-else class="trend-chart">
      <div class="trend-bars">
        <div
          v-for="point in points"
          :key="point.week_start"
          class="trend-col"
          :title="
            `${shortWeek(point.week_start)} · ${point.avg_cycle_days}d ` +
            `· ${point.n_buds} BUD${point.n_buds === 1 ? '' : 's'}`
          "
        >
          <div
            class="trend-col__bar"
            :style="{ height: `${barHeight(point.avg_cycle_days)}%` }"
          >
            <span class="trend-col__value">{{ point.avg_cycle_days.toFixed(1) }}d</span>
          </div>
          <div class="trend-col__label">{{ shortWeek(point.week_start) }}</div>
          <div class="trend-col__count">{{ point.n_buds }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { VelocityTrendPoint } from '@/composables/useLearningsOverview'

const props = defineProps<{ points: VelocityTrendPoint[] }>()

const maxCycleDays = computed(() => {
  if (props.points.length === 0) return 1
  return Math.max(1, ...props.points.map((p) => p.avg_cycle_days))
})

function barHeight(value: number): number {
  return Math.max(6, Math.round((value / maxCycleDays.value) * 100))
}

function shortWeek(weekStart: string): string {
  const date = new Date(weekStart)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 12px;
  padding: 18px 20px 20px;
  background: rgba(var(--v-theme-surface-variant), 0.04);
}

.card__head {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 10px;
  row-gap: 2px;
  margin-bottom: 14px;
}

.card__head > .v-icon {
  grid-row: 1 / span 2;
  align-self: start;
  margin-top: 2px;
}

.card__title {
  font-size: 15px;
  font-weight: 500;
}

.card__sub {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.85;
  max-width: 720px;
}

.empty-row {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  padding: 6px 2px;
}

.trend-chart {
  padding: 4px 0;
}

.trend-bars {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  height: 160px;
  padding: 0 4px;
  overflow-x: auto;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.trend-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 46px;
  height: 100%;
  flex-shrink: 0;
}

.trend-col__bar {
  position: relative;
  width: 28px;
  background: linear-gradient(
    180deg,
    rgba(var(--v-theme-primary), 0.85) 0%,
    rgba(var(--v-theme-primary), 0.45) 100%
  );
  border-radius: 4px 4px 0 0;
  margin-top: auto;
  margin-bottom: 4px;
  transition: height 0.2s ease;
  min-height: 4px;
}

.trend-col__value {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  color: rgb(var(--v-theme-on-surface-variant));
  white-space: nowrap;
  padding-bottom: 2px;
}

.trend-col__label {
  font-size: 10px;
  color: rgb(var(--v-theme-on-surface-variant));
  margin-top: 6px;
}

.trend-col__count {
  font-size: 10px;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.6;
  margin-top: 2px;
}
</style>
