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
  Hero KPI row for the org-level Learnings overview. Four tiles
  matching the AppCallout visual contract: 3px primary accent on the
  left + soft surface-variant gradient + uppercase eyebrow label.

  The "BUDs shipped" tile flips its accent to warning + shows a "cards
  get sharper after ~5 BUDs" hint when totals are below the threshold,
  so the user understands why the downstream cards look sparse.
-->

<template>
  <section class="kpi-row">
    <article class="kpi" :class="{ 'kpi--sparse': totalBudsShipped < 5 }">
      <div class="kpi-label">BUDs shipped · 30d</div>
      <div class="kpi-value">{{ totalBudsShipped }}</div>
      <div v-if="totalBudsShipped < 5" class="kpi-hint">
        Cards below get sharper after ~5 BUDs ship
      </div>
    </article>
    <article class="kpi">
      <div class="kpi-label">Median cycle</div>
      <div class="kpi-value">
        {{ medianCycle != null ? `${medianCycle.toFixed(1)}d` : '—' }}
      </div>
      <div class="kpi-hint">across last 12 weeks</div>
    </article>
    <article class="kpi">
      <div class="kpi-label">Repeat-offender phases</div>
      <div class="kpi-value kpi-value--warn">{{ repeatOffenderCount }}</div>
      <div class="kpi-hint">consistently over estimate</div>
    </article>
    <article class="kpi">
      <div class="kpi-label">Complexity buckets</div>
      <div class="kpi-value">{{ complexityBucketCount }}</div>
      <div class="kpi-hint">populated by the rollup</div>
    </article>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  totalBudsShipped: number
  medianCycle: number | null
  repeatOffenderCount: number
  complexityBucketCount: number
}>()
</script>

<style scoped>
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.kpi {
  position: relative;
  padding: 14px 16px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  background: linear-gradient(
    180deg,
    rgba(var(--v-theme-surface-variant), 0.18) 0%,
    rgba(var(--v-theme-surface-variant), 0.06) 100%
  );
  overflow: hidden;
}

.kpi::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  background: rgb(var(--v-theme-primary));
  opacity: 0.55;
}

.kpi--sparse::before {
  background: rgb(var(--v-theme-warning));
}

.kpi-label {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.85;
  margin-bottom: 4px;
}

.kpi-value {
  font-size: 28px;
  font-weight: 500;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}

.kpi-value--warn {
  color: rgb(var(--v-theme-warning));
}

.kpi-hint {
  margin-top: 6px;
  font-size: 11px;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.75;
}
</style>
