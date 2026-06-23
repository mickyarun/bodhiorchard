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
  Post-close retrospective panel for the BUD detail "Learnings" tab.

  Hosts three summary cards driven by the structured metrics envelope
  (phase-drift table, contributor table, parallelism gauge) plus the
  LLM-written retrospective_md as the primary narrative. The card
  rendering is intentionally simple — no chart library dependency for
  the initial drop; the org-level overview page in the next commit
  is where richer visualisations land.
-->

<template>
  <div class="learnings-panel">
    <!-- Cold state. Reachable only if the row is fetched as null while the
         tab is open (the tab itself is gated on has_learning), so this is
         purely informational — the regenerate affordance lives on the
         recap-missing branch below, which is the real entry point. -->
    <AppCallout
      v-if="!learning && !loading"
      variant="info"
      eyebrow="No recap yet"
      icon="mdi-book-open-page-variant-outline"
    >
      The Learning Agent runs on close when
      <code>auto_generate_phases.closed</code>
      is enabled. Once it has produced a recap, this tab will display
      the retrospective along with phase-drift, contributor, and
      parallelism summaries.
    </AppCallout>

    <v-progress-linear v-if="loading" indeterminate color="primary" />

    <template v-else-if="learning">
      <!-- Headline metrics -->
      <div class="learnings-panel__metric-row">
        <div class="learnings-panel__metric">
          <div class="learnings-panel__metric-label">Cycle time</div>
          <div class="learnings-panel__metric-value">
            {{ formatDays(learning.cycle_time_days) }}
          </div>
        </div>
        <div class="learnings-panel__metric">
          <div class="learnings-panel__metric-label">Original estimate</div>
          <div class="learnings-panel__metric-value">
            {{ formatDays(learning.estimated_days) }}
          </div>
        </div>
        <div class="learnings-panel__metric">
          <div class="learnings-panel__metric-label">Bugs</div>
          <div class="learnings-panel__metric-value">{{ learning.bug_count }}</div>
        </div>
        <div class="learnings-panel__metric">
          <div class="learnings-panel__metric-label">Parallelism</div>
          <div class="learnings-panel__metric-value">
            {{ formatParallelism(learning.metrics?.parallelism_score ?? null) }}
          </div>
        </div>
      </div>

      <!-- Phase drift -->
      <section v-if="phaseRows.length" class="learnings-panel__section">
        <h3 class="learnings-panel__section-title">Phase drift</h3>
        <v-table density="compact" class="learnings-panel__table">
          <thead>
            <tr>
              <th>Phase</th>
              <th class="text-right">Estimated</th>
              <th class="text-right">Actual</th>
              <th class="text-right">Drift</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in phaseRows" :key="row.phase">
              <td>{{ row.phase }}</td>
              <td class="text-right">{{ formatDays(row.estimated_days) }}</td>
              <td class="text-right">{{ formatDays(row.actual_days) }}</td>
              <td class="text-right" :class="driftClass(row.drift_pct)">
                {{ formatDrift(row.drift_pct) }}
              </td>
            </tr>
          </tbody>
        </v-table>
      </section>

      <!-- Contributors -->
      <section v-if="contributorRows.length" class="learnings-panel__section">
        <h3 class="learnings-panel__section-title">Contributors</h3>
        <v-table density="compact" class="learnings-panel__table">
          <thead>
            <tr>
              <th>Name</th>
              <th class="text-right">Commits</th>
              <th class="text-right">PRs merged</th>
              <th class="text-right">TODOs done</th>
              <th class="text-right">Active days</th>
            </tr>
          </thead>
          <tbody>
            <!-- External collaborators have user_id=null but
                 github_login set, so key on whichever is present. -->
            <tr
              v-for="row in contributorRows"
              :key="row.user_id ?? row.github_login ?? row.name"
            >
              <td>{{ row.name }}</td>
              <td class="text-right">{{ row.commits }}</td>
              <td class="text-right">{{ row.prs_merged }}</td>
              <td class="text-right">{{ row.todos_completed }}</td>
              <td class="text-right">{{ row.active_days }}</td>
            </tr>
          </tbody>
        </v-table>
      </section>

      <!-- Retrospective markdown -->
      <section v-if="learning.retrospective_md" class="learnings-panel__section">
        <div class="learnings-panel__section-head">
          <h3 class="learnings-panel__section-title">Retrospective</h3>
          <v-btn
            variant="text"
            size="x-small"
            prepend-icon="mdi-refresh"
            :loading="regenerating"
            @click="onRegenerate"
          >
            Regenerate
          </v-btn>
        </div>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <article class="markdown-body markdown-body--numeric" v-html="renderedRetro" />
      </section>

      <!-- Recap missing (metrics landed but the Learning Agent left no
           retrospective — usually a transient compute/agent failure at
           close). Offer a one-click re-run. -->
      <section v-else class="learnings-panel__section">
        <h3 class="learnings-panel__section-title">Retrospective</h3>
        <AppCallout
          variant="info"
          eyebrow="No recap"
          icon="mdi-book-open-page-variant-outline"
        >
          The metrics above were captured, but the Learning Agent didn't
          leave a written recap. Re-run it to generate one.
        </AppCallout>
        <div class="learnings-panel__actions">
          <v-btn
            variant="tonal"
            size="small"
            color="primary"
            prepend-icon="mdi-refresh"
            :loading="regenerating"
            @click="onRegenerate"
          >
            Generate retrospective
          </v-btn>
          <span v-if="queued" class="learnings-panel__hint">
            Queued — the recap will appear here once the agent finishes.
          </span>
          <span v-else-if="error" class="learnings-panel__hint text-error">{{ error }}</span>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useBudLearning, type BudLearningPhaseMetric } from '@/composables/useBudLearning'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{ budId: string; refreshKey?: number }>()

const { learning, loading, error, regenerating, fetchLearning, regenerateLearning } =
  useBudLearning()

// Set once the regenerate request is accepted (202). The recap lands
// asynchronously; the parent's `learning_recorded` socket event bumps
// `refreshKey`, which re-fetches and reveals the recap — at which point
// this hint is no longer needed.
const queued = ref(false)

watch(
  () => [props.budId, props.refreshKey] as const,
  ([budId]) => {
    if (budId) {
      void fetchLearning(budId)
    }
  },
  { immediate: true },
)

// Clear the "queued" hint once the recap actually arrives.
watch(
  () => learning.value?.retrospective_md,
  (retro) => {
    if (retro) queued.value = false
  },
)

async function onRegenerate(): Promise<void> {
  if (regenerating.value) return
  try {
    await regenerateLearning(props.budId)
    queued.value = true
  } catch {
    // `error` is set by the composable; surfaced inline below.
    queued.value = false
  }
}

interface PhaseRow extends BudLearningPhaseMetric {
  phase: string
}

const phaseRows = computed<PhaseRow[]>(() => {
  const phases = learning.value?.metrics?.phase_metrics ?? {}
  return Object.entries(phases).map(([phase, metric]) => ({ phase, ...metric }))
})

const contributorRows = computed(() => learning.value?.metrics?.contributors ?? [])

const renderedRetro = computed(() => renderMarkdown(learning.value?.retrospective_md ?? ''))

function formatDays(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${value.toFixed(1)}d`
}

function formatDrift(value: number | null | undefined): string {
  if (value == null) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(0)}%`
}

function formatParallelism(value: number | null): string {
  if (value == null) return 'n/a'
  return `${Math.round(value * 100)}%`
}

function driftClass(value: number | null | undefined): string {
  if (value == null) return ''
  if (value >= 50) return 'text-error'
  if (value >= 20) return 'text-warning'
  return 'text-success'
}
</script>

<style scoped>
.learnings-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px 0;
}

.learnings-panel__metric-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.learnings-panel__metric {
  padding: 12px 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
  background: rgba(var(--v-theme-surface-variant), 0.1);
}

.learnings-panel__metric-label {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  margin-bottom: 4px;
}

.learnings-panel__metric-value {
  font-size: 20px;
  font-weight: 500;
}

.learnings-panel__section {
  padding: 12px 16px 16px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
  background: rgba(var(--v-theme-surface-variant), 0.1);
}

.learnings-panel__section-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgba(var(--v-theme-on-surface), 0.7);
  margin: 0 0 8px;
}

.learnings-panel__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.learnings-panel__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.learnings-panel__hint {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}

.learnings-panel__table {
  background: transparent;
}

.learnings-panel__table :deep(.v-table__wrapper) {
  background: transparent;
}

.learnings-panel__table :deep(table) {
  background: transparent;
}
</style>
