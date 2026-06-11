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
  Phase rollup by complexity. Each complexity bucket renders a row per
  tracked phase with: phase name, a horizontal bar (width = p70
  relative to the slowest phase in the bucket, tick mark at p50),
  p50/p70 values, and a 30-day trend pill. Bar widths are
  intentionally bucket-scoped so the relative ordering of phases is
  readable even when the absolute scale differs across buckets.
-->

<template>
  <section class="card">
    <header class="card__head">
      <v-icon icon="mdi-chart-bar" size="18" color="primary" />
      <div class="card__title">Phase rollup by complexity</div>
      <div class="card__sub">
        Rolling percentile bars per phase, scoped to one complexity
        bucket. The bar's length is p70 relative to the slowest
        phase in the bucket; the tick mark shows where p50 lands.
      </div>
    </header>
    <div
      v-for="bucket in buckets"
      :key="bucket.complexity"
      class="bucket"
    >
      <div class="bucket-head">
        <span class="bucket-label">Complexity {{ bucket.complexity }}</span>
        <span class="bucket-meta">
          {{ bucket.n_samples_total }}
          sample{{ bucket.n_samples_total === 1 ? '' : 's' }}
        </span>
      </div>
      <div class="phase-grid">
        <div
          v-for="phase in bucket.phases"
          :key="phase.phase"
          class="phase-row"
        >
          <div class="phase-name">{{ phase.phase }}</div>
          <div class="phase-bar">
            <div
              class="phase-bar__fill"
              :style="{ width: `${phaseFillPct(bucket, phase)}%` }"
            />
            <div
              v-if="phase.p50_days != null"
              class="phase-bar__p50"
              :style="{ left: `${phaseP50Pct(bucket, phase)}%` }"
              :title="`p50 ${phase.p50_days?.toFixed(1)}d`"
            />
          </div>
          <div class="phase-figures">
            <span class="phase-figures__p50">
              p50 {{ fmt(phase.p50_days) }}
            </span>
            <span class="phase-figures__p70">
              · p70 {{ fmt(phase.p70_days) }}
            </span>
            <span
              class="phase-figures__trend"
              :class="trendClass(phase.trend_30d_pct)"
              :title="
                phase.trend_30d_pct == null
                  ? '30-day baseline not yet recorded'
                  : `${phase.trend_30d_pct.toFixed(0)}% vs 30 days ago`
              "
            >
              {{ fmtTrend(phase.trend_30d_pct) }}
            </span>
          </div>
          <div class="phase-n">n={{ phase.n_samples }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import type {
  ComplexityBucket,
  PhaseRollup,
} from '@/composables/useLearningsOverview'

defineProps<{ buckets: ComplexityBucket[] }>()

function bucketMaxP70(bucket: ComplexityBucket): number {
  let max = 0
  for (const phase of bucket.phases) {
    if (phase.p70_days != null && phase.p70_days > max) max = phase.p70_days
  }
  return max || 1
}

function phaseFillPct(bucket: ComplexityBucket, phase: PhaseRollup): number {
  if (phase.p70_days == null) return 0
  const pct = (phase.p70_days / bucketMaxP70(bucket)) * 100
  return Math.max(2, Math.min(100, pct))
}

function phaseP50Pct(bucket: ComplexityBucket, phase: PhaseRollup): number {
  if (phase.p50_days == null) return 0
  return Math.max(0, Math.min(100, (phase.p50_days / bucketMaxP70(bucket)) * 100))
}

function fmt(value: number | null | undefined): string {
  return value == null ? '—' : `${value.toFixed(1)}d`
}

function fmtTrend(value: number | null | undefined): string {
  if (value == null) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(0)}%`
}

function trendClass(value: number | null | undefined): string {
  if (value == null) return 'trend--neutral'
  if (value >= 10) return 'trend--bad'
  if (value <= -10) return 'trend--good'
  return 'trend--neutral'
}
</script>

<style scoped>
.card {
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  padding: 18px 20px 20px;
  background: rgb(var(--v-theme-surface));
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

.bucket {
  padding: 12px 0;
  border-top: 1px dashed rgba(var(--v-theme-on-surface), 0.08);
}

.bucket:first-of-type {
  border-top: none;
  padding-top: 4px;
}

.bucket-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 8px;
}

.bucket-label {
  font-size: 13px;
  font-weight: 500;
}

.bucket-meta {
  font-size: 11px;
  color: rgb(var(--v-theme-on-surface-variant));
}

.phase-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.phase-row {
  display: grid;
  grid-template-columns: 100px minmax(160px, 1fr) auto 56px;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.phase-name {
  color: rgb(var(--v-theme-on-surface));
}

.phase-bar {
  position: relative;
  height: 8px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 4px;
  overflow: hidden;
}

.phase-bar__fill {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(
    90deg,
    rgba(var(--v-theme-primary), 0.55),
    rgba(var(--v-theme-primary), 0.85)
  );
  border-radius: 4px;
  transition: width 0.2s ease;
}

.phase-bar__p50 {
  position: absolute;
  top: -2px;
  bottom: -2px;
  width: 2px;
  background: rgb(var(--v-theme-on-surface));
  opacity: 0.55;
  transform: translateX(-1px);
}

.phase-figures {
  display: flex;
  gap: 4px;
  align-items: baseline;
  white-space: nowrap;
}

.phase-figures__p50 {
  color: rgb(var(--v-theme-on-surface));
}

.phase-figures__p70 {
  color: rgb(var(--v-theme-on-surface-variant));
}

.phase-figures__trend {
  font-size: 11px;
  margin-left: 4px;
}

.trend--good {
  color: rgb(var(--v-theme-success));
}

.trend--bad {
  color: rgb(var(--v-theme-error));
}

.trend--neutral {
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.7;
}

.phase-n {
  text-align: right;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.7;
}
</style>
