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

<!-- Headline numbers for the Learnings page, four across on desktop. -->
<template>
  <section aria-label="Key numbers" class="kpi-row">
    <div v-for="kpi in kpis" :key="kpi.label" class="kpi">
      <span class="kpi__label">{{ kpi.label }}</span>
      <span class="kpi__value">{{ kpi.value }}</span>
      <span class="kpi__sub">{{ kpi.sub }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { LearningsKpi } from '@/utils/learningsOverview'

defineProps<{ kpis: LearningsKpi[] }>()
</script>

<style scoped>
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.kpi {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 18px 20px;
  border-radius: 12px;
  border: 1px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-surface));
}
.kpi__label {
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface-variant));
}
.kpi__value {
  font-size: 30px;
  line-height: 34px;
  font-weight: 600;
  letter-spacing: var(--tracking-display);
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.kpi__sub {
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
@media (max-width: 1100px) {
  .kpi-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 480px) {
  .kpi-row {
    gap: 12px;
  }
  .kpi {
    padding: 14px 16px;
  }
  .kpi__value {
    font-size: 24px;
    line-height: 30px;
  }
}
</style>
