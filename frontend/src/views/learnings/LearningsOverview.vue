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
  Org-level Learnings overview. Composes five cards backed by
  GET /v1/learnings/overview: a KPI hero row plus four visualisation
  sections (phase rollup, repeat offenders, velocity trend, top
  contributors). Each section lives in its own component so the
  individual visualisations stay independently reviewable + the
  overview shell stays under the project's ~200-line file budget.
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
      <LearningsKpiRow
        :total-buds-shipped="totalBudsShipped"
        :median-cycle="medianCycle"
        :repeat-offender-count="overview.repeat_offender_phases.length"
        :complexity-bucket-count="overview.complexity_buckets.length"
      />
      <PhaseRollupCard :buckets="overview.complexity_buckets" />
      <RepeatOffenderCard
        v-if="overview.repeat_offender_phases.length"
        :offenders="overview.repeat_offender_phases"
      />
      <VelocityTrendCard :points="overview.velocity_trend" />
      <TopContributorsCard :contributors="overview.top_contributors" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import LearningsKpiRow from '@/components/learnings/LearningsKpiRow.vue'
import PhaseRollupCard from '@/components/learnings/PhaseRollupCard.vue'
import RepeatOffenderCard from '@/components/learnings/RepeatOffenderCard.vue'
import TopContributorsCard from '@/components/learnings/TopContributorsCard.vue'
import VelocityTrendCard from '@/components/learnings/VelocityTrendCard.vue'
import { useLearningsOverview } from '@/composables/useLearningsOverview'

const { overview, loading, fetchOverview, isEmpty } = useLearningsOverview()

onMounted(() => {
  void fetchOverview()
})

function refresh(): void {
  void fetchOverview(true)
}

const overviewIsEmpty = computed(() => !loading.value && isEmpty(overview.value))

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
</script>

<style scoped>
.learnings-overview {
  max-width: 1180px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

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
</style>
