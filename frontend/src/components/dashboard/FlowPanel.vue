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

<!-- Flow: one stacked bar of BUDs not yet closed, by stage, with a count
     per stage underneath. Each stage keeps its lifecycle colour from the board. -->
<template>
  <AppPanel title="Flow" note="Every BUD not yet closed, by stage">
    <template #action><router-link to="/buds">Open board</router-link></template>

    <div class="flow__bar" role="img" :aria-label="summary">
      <span
        v-for="stage in loading ? [] : filled"
        :key="stage.status"
        class="flow__segment"
        :style="{ flexGrow: stage.count, background: swatch(stage.color) }"
      />
      <span v-if="loading || !filled.length" class="flow__segment flow__segment--empty" />
    </div>

    <div class="flow__legend-box">
      <ul class="flow__legend" :style="{ '--stage-count': stages.length }">
        <li v-for="stage in stages" :key="stage.status" class="flow__stage">
          <span class="flow__name">
            <span class="flow__dot" :style="{ background: swatch(stage.color) }" aria-hidden="true" />
            {{ stage.label }}
          </span>
          <span class="flow__count">{{ loading ? '–' : stage.count }}</span>
        </li>
      </ul>
    </div>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import type { FlowStage } from '@/utils/dashboardOverview'

const props = defineProps<{ stages: FlowStage[]; loading: boolean }>()

const filled = computed(() => props.stages.filter(s => s.count > 0))
const summary = computed(() =>
  props.stages.map(s => `${s.label} ${s.count}`).join(', '),
)

function swatch(themeColor: string): string {
  return `rgb(var(--v-theme-${themeColor}))`
}
</script>

<style scoped>
.flow__bar {
  display: flex;
  gap: 2px;
  height: 10px;
  border-radius: var(--radius-pill);
  overflow: hidden;
  margin-bottom: 12px;
}
.flow__segment {
  flex: 0 1 0;
  min-width: 6px;
}
.flow__segment--empty {
  flex-grow: 1;
  background: rgb(var(--v-theme-surface-variant));
}
/* Every stage on one row when the card is wide enough, else rows of four,
   or three in a phone-width card. */
.flow__legend-box {
  container-type: inline-size;
}
.flow__legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 4px;
}
@container (max-width: 420px) {
  .flow__legend {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@container (min-width: 760px) {
  .flow__legend {
    grid-template-columns: repeat(var(--stage-count), minmax(0, 1fr));
  }
}
.flow__stage {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 4px 8px 0;
  min-width: 0;
}
.flow__name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: rgb(var(--v-theme-on-surface-variant));
}
.flow__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-pill);
  flex-shrink: 0;
}
.flow__count {
  font-size: 20px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
