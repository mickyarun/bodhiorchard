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

<!-- BUDs closed each week across the trend window, the current week
     drawn in the full action blue. -->
<template>
  <AppPanel title="Shipped per week" :note="`BUDs closed in the last ${weeks.length} weeks`">
    <div class="weeks" role="img" :aria-label="chartLabel">
      <span v-for="(week, i) in weeks" :key="week.weekStart" class="week" :title="weekTitle(week)">
        <span class="week__n">{{ week.shipped }}</span>
        <span
          class="week__bar"
          :class="{ 'week__bar--now': i === weeks.length - 1 }"
          :style="{ height: `calc((100% - 24px) * ${week.shipped / peak})` }"
        />
      </span>
    </div>
    <div class="weeks weeks--labels" aria-hidden="true">
      <!-- Every other week is labelled, counting back from this week, so
           the dates never crowd. -->
      <span
        v-for="(week, i) in weeks"
        :key="week.weekStart"
        class="week__label"
        :class="{ 'week__label--skip': (weeks.length - 1 - i) % 2 === 1 }"
      >{{ week.label }}</span>
    </div>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import type { VelocityTrendPoint } from '@/composables/useLearningsOverview'
import { formatDays, weeklyShipped, type WeekBar } from '@/utils/learningsOverview'

const props = defineProps<{ points: VelocityTrendPoint[] }>()

const weeks = computed(() => weeklyShipped(props.points, new Date()))
const peak = computed(() => Math.max(1, ...weeks.value.map(w => w.shipped)))
const chartLabel = computed(
  () => `Shipped per week, oldest first: ${weeks.value.map(w => w.shipped).join(', ')}`,
)

function weekTitle(week: WeekBar): string {
  const cycle = week.avgCycleDays == null ? '' : `, ${formatDays(week.avgCycleDays)} average cycle`
  return `Week of ${week.label}: ${week.shipped} shipped${cycle}`
}
</script>

<style scoped>
.weeks {
  display: grid;
  grid-template-columns: repeat(v-bind('weeks.length'), minmax(0, 1fr));
  gap: 8px;
  align-items: end;
  height: 150px;
  padding-top: 8px;
}
.weeks--labels {
  height: auto;
  padding-top: 8px;
}
.week {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  height: 100%;
  min-width: 0;
}
.week__n {
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-ink-2));
}
.week__bar {
  width: 100%;
  min-height: 3px;
  border-radius: 5px 5px 2px 2px;
  background: rgba(var(--v-theme-primary), 0.4);
}
.week__bar--now {
  background: rgb(var(--v-theme-primary));
}
.week__label {
  font-size: 11px;
  text-align: center;
  white-space: nowrap;
  color: rgb(var(--v-theme-on-surface-variant));
}
.week__label--skip {
  visibility: hidden;
}
</style>
