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

<!-- Median days spent in each lifecycle stage, one stacked bar per BUD
     complexity, coloured by stage. -->
<template>
  <AppPanel title="Where the days go" note="Median days per stage, by complexity">
    <p v-if="rows.length === 0" class="stage-empty">
      Stage timings appear once closed BUDs have a complexity and phase history.
    </p>
    <template v-else>
      <ul class="stage-legend" aria-label="Stages">
        <li v-for="part in legend" :key="part.phase">
          <span class="stage-swatch" :style="{ '--stage': `var(--v-theme-${part.color})` }" />{{ part.label }}
        </li>
      </ul>
      <div v-for="row in rows" :key="row.complexity" class="stage-row">
        <span class="stage-row__name">Complexity {{ row.complexity }}</span>
        <span class="stage-bar" role="img" :aria-label="barLabel(row)">
          <span
            v-for="part in row.parts"
            :key="part.phase"
            class="stage-bar__part"
            :title="`${part.label}: ${formatDays(part.days)} median`"
            :style="{ flexGrow: part.days, '--stage': `var(--v-theme-${part.color})` }"
          />
        </span>
        <span class="stage-row__total">{{ formatDays(row.totalDays) }}</span>
      </div>
      <p class="stage-note">
        Based on {{ sampleCount }} stage timings from closed BUDs. Hover a segment for its stage.
      </p>
    </template>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import type { ComplexityBucket } from '@/composables/useLearningsOverview'
import { formatDays, stageLegend, stageRow, type StageRow } from '@/utils/learningsOverview'

const props = defineProps<{ buckets: ComplexityBucket[] }>()

const rows = computed(() => props.buckets.map(stageRow).filter(r => r.parts.length > 0))
const legend = computed(() => stageLegend(rows.value))
const sampleCount = computed(() => rows.value.reduce((sum, r) => sum + r.samples, 0))

function barLabel(row: StageRow): string {
  return row.parts.map(p => `${p.label} ${formatDays(p.days)}`).join(', ')
}
</script>

<style scoped>
.stage-empty,
.stage-note {
  margin: 0;
  font-size: 13px;
  line-height: 19px;
  color: rgb(var(--v-theme-ink-2));
}
.stage-legend {
  list-style: none;
  margin: 0 0 14px;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  font-size: 12px;
  color: rgb(var(--v-theme-ink-2));
}
.stage-legend li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.stage-swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  background: rgb(var(--stage));
}
.stage-row {
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr) 56px;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}
.stage-row__name {
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
.stage-row__total {
  font-size: 13px;
  font-weight: 600;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.stage-bar {
  display: flex;
  gap: 2px;
  height: 18px;
  border-radius: 5px;
  overflow: hidden;
}
.stage-bar__part {
  flex-basis: 0;
  min-width: 3px;
  background: rgb(var(--stage));
}
@media (max-width: 480px) {
  .stage-row {
    grid-template-columns: 80px minmax(0, 1fr) 44px;
    gap: 8px;
  }
}
</style>
