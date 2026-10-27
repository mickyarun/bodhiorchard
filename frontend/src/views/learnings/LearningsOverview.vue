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

<!-- Org-level Learnings: trends across closed BUDs from
     GET /v1/learnings/overview — headline numbers, where the days go by
     stage, shipped per week, stages that overrun and top contributors. -->
<template>
  <AppPage
    title="Learnings"
    subtitle="What shipped work teaches us. The Learning agent writes up every BUD when it closes."
  >
    <template #actions>
      <v-btn variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="refresh">Refresh</v-btn>
    </template>

    <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>

    <v-progress-linear v-if="loading && !overview" indeterminate color="primary" aria-label="Loading learnings" />

    <AppCallout v-else-if="overviewIsEmpty && !error" variant="info" title="No learnings yet" icon="mdi-book-open-page-variant-outline">
      Close at least one BUD with <code>auto_generate_phases.closed</code> enabled and this page fills in.
      The Learning agent records how long each stage took on every close, so a handful of shipped BUDs
      shows useful trends within a week or two.
    </AppCallout>

    <template v-else-if="overview">
      <LearningsKpiRow :kpis="kpis" />
      <div class="learnings-pair">
        <StageBreakdownCard :buckets="overview.complexity_buckets" />
        <ShippedPerWeekCard :points="overview.velocity_trend" />
      </div>
      <RepeatOffenderCard v-if="overview.repeat_offender_phases.length" :offenders="overview.repeat_offender_phases" />
      <TopContributorsCard :contributors="overview.top_contributors" />
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import LearningsKpiRow from '@/components/learnings/LearningsKpiRow.vue'
import RepeatOffenderCard from '@/components/learnings/RepeatOffenderCard.vue'
import ShippedPerWeekCard from '@/components/learnings/ShippedPerWeekCard.vue'
import StageBreakdownCard from '@/components/learnings/StageBreakdownCard.vue'
import TopContributorsCard from '@/components/learnings/TopContributorsCard.vue'
import { useLearningsOverview } from '@/composables/useLearningsOverview'
import { learningsKpis } from '@/utils/learningsOverview'

const { overview, loading, error, fetchOverview, isEmpty } = useLearningsOverview()

onMounted(() => {
  void fetchOverview()
})

function refresh(): void {
  void fetchOverview(true)
}

const overviewIsEmpty = computed(() => !loading.value && isEmpty(overview.value))

const kpis = computed(() => {
  const view = overview.value
  if (!view) return []
  return learningsKpis(view.velocity_trend, view.complexity_buckets, view.repeat_offender_phases)
})
</script>

<style scoped>
.learnings-pair {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
@media (max-width: 1100px) {
  .learnings-pair {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
