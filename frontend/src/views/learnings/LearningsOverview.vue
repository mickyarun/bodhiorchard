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
  Org-level Learnings overview. Renders four cards driven by
  GET /v1/learnings/overview: complexity-bucket phase percentiles,
  repeat-offender phases, weekly velocity trend, top contributors.
  No chart library — bar widths are computed inline so the initial
  drop has zero new frontend deps. Richer visualisations land in a
  follow-up once we see real data.
-->

<template>
  <div class="learnings-overview pa-6">
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h1 class="text-h5 font-weight-medium">Learnings overview</h1>
        <div class="text-caption text-medium-emphasis">
          Trends across closed BUDs in this org. Updated as the Learning
          Agent processes each close.
        </div>
      </div>
      <v-btn
        variant="text"
        density="comfortable"
        prepend-icon="mdi-refresh"
        :loading="loading"
        @click="refresh"
      >
        Refresh
      </v-btn>
    </div>

    <v-progress-linear v-if="loading && !overview" indeterminate color="primary" />

    <AppCallout
      v-else-if="overviewIsEmpty"
      variant="info"
      eyebrow="No data yet"
      icon="mdi-book-open-page-variant-outline"
    >
      Close 5+ BUDs to start seeing trends. The Learning Agent populates
      this overview automatically when BUDs are closed with
      <code>auto_generate_phases.closed</code> enabled.
    </AppCallout>

    <template v-else-if="overview">
      <!-- Complexity buckets -->
      <v-card
        v-if="overview.complexity_buckets.length"
        variant="outlined"
        class="learnings-overview__card mb-4"
      >
        <v-card-title class="text-body-1 font-weight-medium">
          Phase rollup by complexity
        </v-card-title>
        <v-card-text>
          <div
            v-for="bucket in overview.complexity_buckets"
            :key="bucket.complexity"
            class="learnings-overview__bucket mb-4"
          >
            <div class="text-body-2 font-weight-medium mb-2">
              Complexity {{ bucket.complexity }}
              <span class="text-caption text-medium-emphasis">
                · {{ bucket.n_samples_total }} sample{{ bucket.n_samples_total === 1 ? '' : 's' }}
              </span>
            </div>
            <v-table density="compact">
              <thead>
                <tr>
                  <th>Phase</th>
                  <th class="text-right">n</th>
                  <th class="text-right">p50 (d)</th>
                  <th class="text-right">p70 (d)</th>
                  <th class="text-right">p85 (d)</th>
                  <th class="text-right">30d trend</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="phase in bucket.phases" :key="phase.phase">
                  <td>{{ phase.phase }}</td>
                  <td class="text-right">{{ phase.n_samples }}</td>
                  <td class="text-right">{{ fmt(phase.p50_days) }}</td>
                  <td class="text-right">{{ fmt(phase.p70_days) }}</td>
                  <td class="text-right">{{ fmt(phase.p85_days) }}</td>
                  <td class="text-right" :class="trendClass(phase.trend_30d_pct)">
                    {{ fmtTrend(phase.trend_30d_pct) }}
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </v-card-text>
      </v-card>

      <!-- Repeat offenders -->
      <v-card
        v-if="overview.repeat_offender_phases.length"
        variant="outlined"
        class="learnings-overview__card mb-4"
      >
        <v-card-title class="text-body-1 font-weight-medium">
          Repeat-offender phases
        </v-card-title>
        <v-card-text>
          <v-table density="compact">
            <thead>
              <tr>
                <th>Phase</th>
                <th class="text-right">Median drift</th>
                <th class="text-right">Over estimate</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in overview.repeat_offender_phases" :key="row.phase">
                <td>{{ row.phase }}</td>
                <td class="text-right text-error">
                  +{{ row.median_drift_pct.toFixed(0) }}%
                </td>
                <td class="text-right">
                  {{ row.buds_over_estimate }}/{{ row.buds_total }}
                </td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>

      <!-- Velocity trend -->
      <v-card
        v-if="overview.velocity_trend.length"
        variant="outlined"
        class="learnings-overview__card mb-4"
      >
        <v-card-title class="text-body-1 font-weight-medium">
          Velocity trend (avg cycle days per week)
        </v-card-title>
        <v-card-text>
          <div class="learnings-overview__bars">
            <div
              v-for="point in overview.velocity_trend"
              :key="point.week_start"
              class="learnings-overview__bar"
              :title="`${point.week_start}: ${point.avg_cycle_days}d (${point.n_buds} BUD${point.n_buds === 1 ? '' : 's'})`"
            >
              <div
                class="learnings-overview__bar-fill"
                :style="{ height: `${barHeight(point.avg_cycle_days)}px` }"
              />
              <div class="learnings-overview__bar-label">
                {{ shortWeek(point.week_start) }}
              </div>
            </div>
          </div>
        </v-card-text>
      </v-card>

      <!-- Top contributors -->
      <v-card
        v-if="overview.top_contributors.length"
        variant="outlined"
        class="learnings-overview__card"
      >
        <v-card-title class="text-body-1 font-weight-medium">
          Top contributors · last 30 days
        </v-card-title>
        <v-card-text>
          <v-table density="compact">
            <thead>
              <tr>
                <th>Name</th>
                <th class="text-right">BUDs shipped</th>
                <th class="text-right">Commits</th>
                <th class="text-right">PRs merged</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in overview.top_contributors" :key="row.user_id">
                <td>{{ row.name }}</td>
                <td class="text-right">{{ row.buds_shipped_30d }}</td>
                <td class="text-right">{{ row.total_commits_30d }}</td>
                <td class="text-right">{{ row.total_prs_merged_30d }}</td>
              </tr>
            </tbody>
          </v-table>
        </v-card-text>
      </v-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useLearningsOverview } from '@/composables/useLearningsOverview'

const { overview, loading, fetchOverview, isEmpty } = useLearningsOverview()

onMounted(() => {
  void fetchOverview()
})

function refresh(): void {
  void fetchOverview(true)
}

const overviewIsEmpty = computed(() => !loading.value && isEmpty(overview.value))

const maxCycleDays = computed(() => {
  if (!overview.value) return 1
  return Math.max(
    1,
    ...overview.value.velocity_trend.map((p) => p.avg_cycle_days),
  )
})

function fmt(value: number | null | undefined): string {
  return value == null ? '—' : value.toFixed(1)
}

function fmtTrend(value: number | null | undefined): string {
  if (value == null) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(0)}%`
}

function trendClass(value: number | null | undefined): string {
  if (value == null) return ''
  if (value >= 10) return 'text-error'
  if (value <= -10) return 'text-success'
  return ''
}

function barHeight(value: number): number {
  const max = maxCycleDays.value
  return Math.max(4, Math.round((value / max) * 80))
}

function shortWeek(weekStart: string): string {
  // YYYY-MM-DD → "MMM DD"
  const date = new Date(weekStart)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.learnings-overview {
  max-width: 1100px;
  margin: 0 auto;
}

.learnings-overview__card {
  border-color: rgba(var(--v-theme-on-surface), 0.08);
}

.learnings-overview__bucket:last-child {
  margin-bottom: 0 !important;
}

.learnings-overview__bars {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 110px;
  padding: 4px 0;
  overflow-x: auto;
}

.learnings-overview__bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 36px;
}

.learnings-overview__bar-fill {
  width: 100%;
  background: rgb(var(--v-theme-primary));
  border-radius: 3px 3px 0 0;
}

.learnings-overview__bar-label {
  font-size: 10px;
  color: rgb(var(--v-theme-on-surface-variant));
  margin-top: 4px;
  text-align: center;
  white-space: nowrap;
}
</style>
