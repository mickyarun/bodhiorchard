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

<!-- Stages that ran more than 30% over estimate on two or more of the
     last 50 closed BUDs, worst median overrun first. The parent hides the
     panel when there are none. -->
<template>
  <AppPanel title="Stages that run over" note="More than 30% over estimate on two or more of the last 50 closed BUDs" flush>
    <ul class="offenders">
      <li v-for="row in offenders" :key="row.phase" class="offender">
        <span class="offender__stage">{{ stageLabel(row.phase) }}</span>
        <span class="offender__ratio">{{ row.buds_over_estimate }} of {{ row.buds_total }} BUDs over estimate</span>
        <AppTag color="warning" sr-prefix="Median overrun">+{{ row.median_drift_pct.toFixed(0) }}%</AppTag>
      </li>
    </ul>
  </AppPanel>
</template>

<script setup lang="ts">
import AppPanel from '@/components/common/AppPanel.vue'
import AppTag from '@/components/common/AppTag.vue'
import type { RepeatOffender } from '@/composables/useLearningsOverview'
import { stageLabel } from '@/utils/learningsOverview'

defineProps<{ offenders: RepeatOffender[] }>()
</script>

<style scoped>
.offenders {
  list-style: none;
  margin: 0;
  padding: 0;
}
.offender {
  display: grid;
  grid-template-columns: minmax(0, 160px) minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 12px 20px;
  border-top: 1px solid rgb(var(--v-theme-rule));
  font-size: 14px;
}
.offender__stage {
  font-weight: 500;
}
.offender__ratio {
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
@media (max-width: 480px) {
  .offender {
    grid-template-columns: minmax(0, 1fr) auto;
  }
  .offender__ratio {
    grid-column: 1;
  }
}
</style>
