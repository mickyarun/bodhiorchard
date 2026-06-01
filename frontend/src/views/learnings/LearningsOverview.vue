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
  Org-level Learnings overview. Hero KPI tiles + four visualisation
  cards driven by GET /v1/learnings/overview. Hand-rolled bars/
  sparkline keep the component dep-free; idiom mirrors the in-house
  BUDEstimateTimeline range-bar component (horizontal track + filled
  segment + positioned percentile dots) so the page reads as part of
  the same product, not a foreign import.
-->

<template>
  <div class="learnings-overview pa-6">
    <header class="overview-header">
      <div class="overview-title-wrap">
        <div class="overview-eyebrow">Organization</div>
        <h1 class="overview-title">Learnings</h1>
        <div class="overview-sub">
          Trends across closed BUDs in this org. Updated as the Learning
          Agent processes each close.
        </div>
      </div>
      <v-btn
        variant="text"
        density="comfortable"
        prepend-icon="mdi-refresh"
        :loading="loading"
        class="text-none"
        @click="refresh"
      >
        Refresh
      </v-btn>
    </header>

    <v-progress-linear v-if="loading && !overview" indeterminate color="primary" />

    <AppCallout
      v-else-if="overviewIsEmpty"
      variant="info"
      eyebrow="No data yet"
      icon="mdi-book-open-page-variant-outline"
    >
      Close at least one BUD with <code>auto_generate_phases.closed</code>
      enabled and the dashboard fills in automatically. The Learning
      Agent writes per-phase actuals on every close, so even a handful
      of shipped BUDs produces meaningful trends within a week or two.
    </AppCallout>

    <template v-else-if="overview">
      <!-- ── Hero KPIs ─────────────────────────────────────────── -->
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
          <div class="kpi-value kpi-value--warn">
            {{ overview.repeat_offender_phases.length }}
          </div>
          <div class="kpi-hint">consistently over estimate</div>
        </article>
        <article class="kpi">
          <div class="kpi-label">Complexity buckets</div>
          <div class="kpi-value">{{ overview.complexity_buckets.length }}</div>
          <div class="kpi-hint">populated by the rollup</div>
        </article>
      </section>

      <!-- ── Phase rollup by complexity ────────────────────────── -->
      <section class="overview-card">
        <header class="overview-card__head">
          <v-icon icon="mdi-chart-bar" size="18" color="primary" />
          <div class="overview-card__title">Phase rollup by complexity</div>
          <div class="overview-card__sub">
            Rolling percentile bars per phase, scoped to one complexity
            bucket. The bar's length is p70 relative to the slowest
            phase in the bucket; the tick mark shows where p50 lands.
          </div>
        </header>
        <div
          v-for="bucket in overview.complexity_buckets"
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

      <!-- ── Repeat-offender phases ─────────────────────────────── -->
      <section
        v-if="overview.repeat_offender_phases.length"
        class="overview-card"
      >
        <header class="overview-card__head">
          <v-icon icon="mdi-alert-circle-outline" size="18" color="warning" />
          <div class="overview-card__title">Repeat-offender phases</div>
          <div class="overview-card__sub">
            Phases whose median drift across the last 50 closes is above
            the +30% threshold the recap also uses to flag drift.
          </div>
        </header>
        <div class="offender-list">
          <article
            v-for="row in overview.repeat_offender_phases"
            :key="row.phase"
            class="offender"
          >
            <div class="offender-phase">{{ row.phase }}</div>
            <div class="offender-drift">
              +{{ row.median_drift_pct.toFixed(0) }}%
              <span class="offender-drift__label">median drift</span>
            </div>
            <div class="offender-ratio">
              {{ row.buds_over_estimate }} of {{ row.buds_total }} BUDs
              over estimate
            </div>
            <div class="offender-bar">
              <div
                class="offender-bar__fill"
                :style="{
                  width: `${(row.buds_over_estimate / Math.max(1, row.buds_total)) * 100}%`,
                }"
              />
            </div>
          </article>
        </div>
      </section>

      <!-- ── Velocity trend ─────────────────────────────────────── -->
      <section class="overview-card">
        <header class="overview-card__head">
          <v-icon icon="mdi-finance" size="18" color="primary" />
          <div class="overview-card__title">Velocity trend</div>
          <div class="overview-card__sub">
            Average cycle days per week of closures. Bar height is
            relative to the busiest week in this 12-week window.
          </div>
        </header>
        <div v-if="overview.velocity_trend.length === 0" class="empty-row">
          No closures recorded in the last 12 weeks.
        </div>
        <div v-else class="trend-chart">
          <div class="trend-bars">
            <div
              v-for="point in overview.velocity_trend"
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

      <!-- ── Top contributors ──────────────────────────────────── -->
      <section class="overview-card">
        <header class="overview-card__head">
          <v-icon icon="mdi-account-group-outline" size="18" color="primary" />
          <div class="overview-card__title">Top contributors</div>
          <div class="overview-card__sub">
            Last 30 days. Ranked by BUDs shipped; commits and PRs are
            the per-contributor totals across those BUDs.
          </div>
        </header>
        <div v-if="overview.top_contributors.length === 0" class="empty-row">
          No closures with contributors recorded in the last 30 days.
        </div>
        <div v-else class="contrib-list">
          <article
            v-for="(row, idx) in overview.top_contributors"
            :key="row.user_id"
            class="contrib"
          >
            <div class="contrib-rank">{{ idx + 1 }}</div>
            <div class="contrib-avatar" :style="avatarStyle(row.user_id)">
              {{ initials(row.name) }}
            </div>
            <div class="contrib-info">
              <div class="contrib-name">{{ row.name }}</div>
              <div class="contrib-stats">
                {{ row.buds_shipped_30d }}
                BUD{{ row.buds_shipped_30d === 1 ? '' : 's' }} ·
                {{ row.total_commits_30d }} commits ·
                {{ row.total_prs_merged_30d }} PRs
              </div>
            </div>
            <div class="contrib-bar-wrap">
              <div
                class="contrib-bar"
                :style="{ width: `${contributorPct(row)}%` }"
              />
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import {
  useLearningsOverview,
  type ComplexityBucket,
  type PhaseRollup,
  type TopContributor,
} from '@/composables/useLearningsOverview'

const { overview, loading, fetchOverview, isEmpty } = useLearningsOverview()

onMounted(() => {
  void fetchOverview()
})

function refresh(): void {
  void fetchOverview(true)
}

const overviewIsEmpty = computed(() => !loading.value && isEmpty(overview.value))

// ── KPI hero ────────────────────────────────────────────────
const totalBudsShipped = computed(() =>
  (overview.value?.top_contributors ?? []).reduce((sum, c) => sum + c.buds_shipped_30d, 0),
)

const medianCycle = computed<number | null>(() => {
  const points = overview.value?.velocity_trend ?? []
  if (points.length === 0) return null
  const sorted = [...points].map((p) => p.avg_cycle_days).sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
})

// ── Phase rollup bars ───────────────────────────────────────
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

// ── Velocity trend chart ────────────────────────────────────
const maxCycleDays = computed(() => {
  const points = overview.value?.velocity_trend ?? []
  if (points.length === 0) return 1
  return Math.max(1, ...points.map((p) => p.avg_cycle_days))
})

function barHeight(value: number): number {
  return Math.max(6, Math.round((value / maxCycleDays.value) * 100))
}

function shortWeek(weekStart: string): string {
  const date = new Date(weekStart)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// ── Contributors ────────────────────────────────────────────
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2)
  return parts.map((p) => p[0] || '').join('').toUpperCase() || '?'
}

function avatarStyle(seed: string): { background: string } {
  // Deterministic tint per user_id so the same contributor always
  // shows the same avatar colour across renders. Hash → hue, fixed
  // saturation / lightness keeps the palette inside the design system.
  let hash = 0
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffff
  const hue = hash % 360
  return { background: `hsl(${hue}, 55%, 30%)` }
}

function contributorPct(row: TopContributor): number {
  const top = Math.max(1, ...(overview.value?.top_contributors ?? []).map((c) => c.buds_shipped_30d))
  return Math.max(4, Math.round((row.buds_shipped_30d / top) * 100))
}
</script>

<style scoped>
.learnings-overview {
  max-width: 1180px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ── Header ───────────────────────────────────────────────── */
.overview-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}

.overview-eyebrow {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.7;
}

.overview-title {
  font-size: 24px;
  font-weight: 500;
  line-height: 1.1;
  margin: 2px 0 4px;
}

.overview-sub {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
  max-width: 560px;
}

/* ── KPI tiles ────────────────────────────────────────────── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.kpi {
  position: relative;
  padding: 14px 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 12px;
  background: linear-gradient(
    180deg,
    rgba(var(--v-theme-surface-variant), 0.18) 0%,
    rgba(var(--v-theme-surface-variant), 0.06) 100%
  );
  overflow: hidden;
}

.kpi::before {
  content: "";
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

/* ── Card shell ───────────────────────────────────────────── */
.overview-card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 12px;
  padding: 18px 20px 20px;
  background: rgba(var(--v-theme-surface-variant), 0.04);
}

.overview-card__head {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 10px;
  row-gap: 2px;
  margin-bottom: 14px;
}

.overview-card__head > .v-icon {
  grid-row: 1 / span 2;
  align-self: start;
  margin-top: 2px;
}

.overview-card__title {
  font-size: 15px;
  font-weight: 500;
}

.overview-card__sub {
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

/* ── Phase rollup ─────────────────────────────────────────── */
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

/* ── Repeat-offender list ────────────────────────────────── */
.offender-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.offender {
  display: grid;
  grid-template-columns: 140px auto 1fr;
  grid-template-rows: auto auto;
  column-gap: 16px;
  row-gap: 4px;
  align-items: baseline;
  padding: 10px 12px;
  border: 1px solid rgba(var(--v-theme-error), 0.16);
  border-radius: 8px;
  background: rgba(var(--v-theme-error), 0.05);
}

.offender-phase {
  font-size: 13px;
  font-weight: 500;
  grid-row: 1 / span 2;
  align-self: center;
}

.offender-drift {
  font-size: 18px;
  font-weight: 500;
  color: rgb(var(--v-theme-error));
  font-variant-numeric: tabular-nums;
}

.offender-drift__label {
  font-size: 11px;
  font-weight: 400;
  color: rgb(var(--v-theme-on-surface-variant));
  margin-left: 6px;
}

.offender-ratio {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  grid-row: 2;
  grid-column: 2;
}

.offender-bar {
  grid-row: 1 / span 2;
  align-self: center;
  height: 6px;
  background: rgba(var(--v-theme-error), 0.12);
  border-radius: 3px;
  overflow: hidden;
  max-width: 240px;
}

.offender-bar__fill {
  height: 100%;
  background: rgb(var(--v-theme-error));
  opacity: 0.7;
  transition: width 0.2s ease;
}

/* ── Velocity trend ──────────────────────────────────────── */
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

/* ── Contributors ─────────────────────────────────────────── */
.contrib-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.contrib {
  display: grid;
  grid-template-columns: 24px 36px 1fr 120px;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 8px;
}

.contrib-rank {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.contrib-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 500;
  color: white;
  letter-spacing: 0.04em;
}

.contrib-info {
  display: flex;
  flex-direction: column;
}

.contrib-name {
  font-size: 13px;
  font-weight: 500;
}

.contrib-stats {
  font-size: 11px;
  color: rgb(var(--v-theme-on-surface-variant));
}

.contrib-bar-wrap {
  height: 6px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 3px;
  overflow: hidden;
}

.contrib-bar {
  height: 100%;
  background: linear-gradient(
    90deg,
    rgba(var(--v-theme-primary), 0.4),
    rgba(var(--v-theme-primary), 0.9)
  );
  border-radius: 3px;
  transition: width 0.2s ease;
}
</style>
