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

<!-- Headline numbers: one linked tile each, four across on desktop, two
     on tablets, stacked pairs on phones. -->
<template>
  <section aria-label="Key numbers" class="kpi-tiles">
    <router-link v-for="kpi in kpis" :key="kpi.label" :to="kpi.to" class="kpi-tile">
      <span class="kpi-tile__label">{{ kpi.label }}</span>
      <span class="kpi-tile__value">{{ kpi.value }}</span>
      <span class="kpi-tile__sub">{{ kpi.sub }}</span>
    </router-link>
  </section>
</template>

<script setup lang="ts">
import type { Kpi } from '@/utils/dashboardOverview'

defineProps<{ kpis: Kpi[] }>()
</script>

<style scoped>
.kpi-tiles {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.kpi-tile {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 18px 20px;
  border-radius: 12px;
  border: 1px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-surface));
  color: inherit;
  text-decoration: none;
  transition: border-color var(--dur-short) var(--ease-out);
}
.kpi-tile:hover {
  border-color: rgba(var(--v-theme-primary), 0.5);
}
.kpi-tile:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}
.kpi-tile__label {
  font-size: 13px;
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface-variant));
}
.kpi-tile__value {
  font-size: 30px;
  line-height: 34px;
  font-weight: 600;
  letter-spacing: var(--tracking-display);
  font-variant-numeric: tabular-nums;
}
.kpi-tile__sub {
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
@media (max-width: 1100px) {
  .kpi-tiles {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 480px) {
  .kpi-tiles {
    gap: 12px;
  }
  .kpi-tile {
    padding: 14px 16px;
  }
  .kpi-tile__value {
    font-size: 26px;
    line-height: 30px;
  }
}
</style>
