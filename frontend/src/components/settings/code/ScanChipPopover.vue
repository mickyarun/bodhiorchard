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
  Click-target chip + popover used by ScanRowTrack and
  ScanFinalizationRow. Renders a phase dot and, on click, a v-menu
  with reviewable artifacts:

    - duration / input → kept / dropped (always visible)
    - error message (when present)
    - synthesized features list (FEATURE_SYNTHESIS / FEATURE_MERGE)
    - stage metadata as a key/value grid (everything else in extras)

  Pure presentational — store-agnostic.
-->
<template>
  <v-menu
    v-model="open"
    :close-on-content-click="false"
    location="bottom"
    offset="6"
  >
    <template #activator="{ props: act }">
      <button
        v-bind="act"
        type="button"
        class="dot"
        :class="dotClass"
        :title="tooltip"
        :aria-label="`${phase}: ${status}`"
      />
    </template>

    <div class="popover">
      <header class="popover-head">
        <span class="popover-title">{{ phase }}</span>
        <span class="popover-status">{{ status }}</span>
      </header>

      <div v-if="!step" class="popover-empty">
        Not started yet.
      </div>

      <template v-else>
        <div v-if="skippedReason" class="popover-callout">
          <v-icon icon="mdi-skip-next-circle-outline" size="14" />
          <span>{{ skippedReason }}</span>
        </div>

        <dl class="popover-grid">
          <div>
            <dt>duration</dt>
            <dd>{{ formatDuration(step.duration_ms) }}</dd>
          </div>
          <div>
            <dt>{{ ioLabel }}</dt>
            <dd>{{ reductionLine }}</dd>
          </div>
        </dl>

        <p v-if="step.error" class="popover-error">
          <strong>error:</strong> {{ step.error }}
        </p>

        <section v-if="toolProgress" class="tool-progress">
          <h4 class="tool-progress__title">Live model activity</h4>
          <p class="tool-progress__line">
            {{ toolProgress.total }} tool {{ toolProgress.total === 1 ? 'call' : 'calls' }}
            <template v-if="toolProgress.lastTool">
              · last: <code>{{ toolProgress.lastTool }}</code>
            </template>
          </p>
          <ul v-if="toolProgress.byTool.length" class="tool-progress__list">
            <li v-for="entry in toolProgress.byTool" :key="entry.name">
              <code>{{ entry.name }}</code>
              <span class="tool-progress__count">×{{ entry.count }}</span>
            </li>
          </ul>
        </section>

        <ScanSubStageTrail v-if="subStages.length > 1" :stages="subStages" />

        <ScanFeatureList v-if="features.length" :features="features" />

        <section v-if="metadataEntries.length" class="meta">
          <h4 class="meta__title">Stage metadata</h4>
          <dl class="meta__grid">
            <div v-for="entry in metadataEntries" :key="entry.key">
              <dt>{{ entry.key }}</dt>
              <dd>{{ entry.value }}</dd>
            </div>
          </dl>
        </section>
      </template>
    </div>
  </v-menu>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import ScanFeatureList, { type ProducedFeature } from './ScanFeatureList.vue'
import ScanSubStageTrail, { type SubStage } from './ScanSubStageTrail.vue'
import type { ScanPhase, StepRow, StepStatus } from '@/stores/reposcanv2Scans'

const props = defineProps<{
  phase: ScanPhase
  step: StepRow | null
}>()

const open = ref(false)

const status = computed<StepStatus | 'pending'>(() => props.step?.status ?? 'pending')

const dotClass = computed(() => ({
  'dot--queued': status.value === 'queued' || status.value === 'pending',
  'dot--running': status.value === 'running',
  'dot--done': status.value === 'done',
  'dot--failed': status.value === 'failed',
  'dot--skipped': status.value === 'skipped' || status.value === 'skipped_cache',
}))

const features = computed<ProducedFeature[]>(() => {
  const raw = props.step?.extras?.produced_features
  if (!Array.isArray(raw)) return []
  return raw.filter((f): f is ProducedFeature =>
    !!f && typeof f === 'object' && typeof (f as ProducedFeature).title === 'string',
  )
})

interface MetadataEntry { key: string; value: string }

// Keys hoisted to first-class popover sections — exclude from the
// generic metadata grid so they're not rendered twice.
const PROMOTED_KEYS: ReadonlySet<string> = new Set([
  'produced_features',
  'sub_stages',
  'io_label',
  'skipped_reason',
  // ``tool_progress`` is rendered as its own section above; suppress
  // the auto-flattened entry that would otherwise dump the whole
  // counter object into the metadata grid.
  'tool_progress',
  // ``input_count`` / ``kept_count`` / ``dropped_count`` may live in
  // extras when a stage promotes its counts there; the workflow has
  // already lifted them onto the step row so the grid would just
  // duplicate the reduction line.
  'input_count',
  'kept_count',
  'dropped_count',
])

const subStages = computed<SubStage[]>(() => {
  const raw = props.step?.extras?.sub_stages
  if (!Array.isArray(raw)) return []
  return raw.filter((s): s is SubStage =>
    !!s && typeof s === 'object' && typeof (s as SubStage).name === 'string',
  )
})

const ioLabel = computed<string>(() => {
  const raw = props.step?.extras?.io_label
  return typeof raw === 'string' && raw.length > 0 ? raw : 'in → kept / dropped'
})

interface ToolProgressView {
  total: number
  lastTool: string | null
  byTool: { name: string; count: number }[]
}

// Surfaces the in-memory tool-use counter (set server-side from the
// stream-json progress callback) for the running feature_synthesis
// chip. Returns null when the run hasn't started or no tool has been
// invoked yet — in which case the popover stays unchanged.
const toolProgress = computed<ToolProgressView | null>(() => {
  const raw = props.step?.extras?.tool_progress
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const total = typeof obj.total === 'number' ? obj.total : 0
  if (total === 0) return null
  const lastTool = typeof obj.last_tool === 'string' ? obj.last_tool : null
  const byToolRaw = obj.by_tool
  const byTool: { name: string; count: number }[] = []
  if (byToolRaw && typeof byToolRaw === 'object') {
    for (const [name, count] of Object.entries(byToolRaw)) {
      if (typeof count === 'number') byTool.push({ name, count })
    }
    byTool.sort((a, b) => b.count - a.count)
  }
  return { total, lastTool, byTool }
})

const reductionLine = computed<string>(() => {
  const step = props.step
  if (!step) return '—'
  return `${step.input_count} → ${step.kept_count} / ${step.dropped_count}`
})

const skippedReason = computed<string | null>(() => {
  const raw = props.step?.extras?.skipped_reason
  if (typeof raw === 'string' && raw.length > 0) return raw
  // Fall back when the status is skipped but no reason was supplied —
  // better than a silent chip.
  if (props.step?.status === 'skipped_cache' || props.step?.status === 'skipped') {
    return 'Output cached from a prior scan'
  }
  return null
})

// Everything in extras that isn't a promoted artifact list — flattened
// into a key/value grid so the user reads names, not raw JSON.
const metadataEntries = computed<MetadataEntry[]>(() => {
  const extras = props.step?.extras
  if (!extras) return []
  return Object.entries(extras)
    .filter(([key]) => !PROMOTED_KEYS.has(key))
    .map(([key, value]) => ({ key, value: formatScalar(value) }))
})

function formatScalar(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    return Number.isInteger(value) ? value.toLocaleString() : value.toString()
  }
  if (typeof value === 'boolean' || typeof value === 'string') return String(value)
  if (Array.isArray(value)) return value.length === 0 ? '—' : `[${value.length} items]`
  if (typeof value === 'object') return '{…}'
  return String(value)
}

const tooltip = computed(() => {
  const step = props.step
  if (!step) return `${props.phase}: not yet started`
  const parts = [`${props.phase} · ${step.status}`]
  if (step.input_count || step.kept_count || step.dropped_count) {
    parts.push(`in ${step.input_count} → kept ${step.kept_count} / dropped ${step.dropped_count}`)
  }
  if (step.duration_ms !== null) parts.push(formatDuration(step.duration_ms))
  if (step.error) parts.push(`error: ${step.error}`)
  return parts.join('\n')
})

function formatDuration(ms: number | null): string {
  if (ms === null) return '—'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.round(ms / 1000 / 60)}m ${Math.round((ms / 1000) % 60)}s`
}
</script>

<style scoped>
.dot {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  background: rgba(var(--v-theme-on-surface), 0.06);
  cursor: pointer;
  padding: 0;
  transition: transform 100ms ease, box-shadow 100ms ease, background 100ms ease;
}
.dot:hover { transform: scale(1.2); }

.dot--running {
  background: rgb(var(--v-theme-primary));
  border-color: rgb(var(--v-theme-primary));
  animation: dot-pulse 1.4s ease-in-out infinite;
}
@keyframes dot-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(var(--v-theme-primary), 0.45); }
  50%      { box-shadow: 0 0 0 6px rgba(var(--v-theme-primary), 0); }
}
.dot--done    { background: rgb(var(--v-theme-success)); border-color: rgb(var(--v-theme-success)); }
.dot--failed  { background: rgb(var(--v-theme-error)); border-color: rgb(var(--v-theme-error)); }
.dot--skipped { background: rgb(var(--v-theme-info)); border-color: rgb(var(--v-theme-info)); opacity: 0.7; }

.popover {
  min-width: 280px;
  max-width: 360px;
  padding: 12px 14px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  border-radius: 8px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
  display: flex; flex-direction: column; gap: 8px;
}
.popover-head { display: flex; align-items: baseline; gap: 10px; }
.popover-title {
  font-weight: 600; font-size: 0.85rem;
  font-family: var(--v-font-family-monospace, monospace);
}
.popover-status {
  font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.popover-empty { font-size: 0.8rem; font-style: italic; color: rgba(var(--v-theme-on-surface), 0.55); }
.popover-grid {
  margin: 0;
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 8px;
}
.popover-grid dt {
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.05em;
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.popover-grid dd {
  margin: 1px 0 0; font-family: var(--v-font-family-monospace, monospace);
  font-size: 0.78rem; color: rgba(var(--v-theme-on-surface), 0.85);
}
.popover-error {
  margin: 0; font-size: 0.78rem; color: rgb(var(--v-theme-error));
  font-family: var(--v-font-family-monospace, monospace);
}
.popover-callout {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgba(var(--v-theme-info), 0.10);
  border: 1px solid rgba(var(--v-theme-info), 0.35);
  color: rgb(var(--v-theme-info));
  font-size: 0.76rem;
  line-height: 1.3;
}

.tool-progress {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-top: 1px dashed rgba(var(--v-theme-on-surface), 0.08);
  padding-top: 8px;
}
.tool-progress__title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgb(var(--v-theme-on-surface));
  opacity: 0.7;
  margin: 0;
}
.tool-progress__line {
  font-size: 12px;
  margin: 0;
  color: rgb(var(--v-theme-on-surface));
  opacity: 0.85;
}
.tool-progress__line code,
.tool-progress__list code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  padding: 1px 5px;
  border-radius: 3px;
}
.tool-progress__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
}
.tool-progress__list li {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}
.tool-progress__count {
  color: rgb(var(--v-theme-on-surface));
  opacity: 0.6;
}

.meta { display: flex; flex-direction: column; gap: 6px; }
.meta__title {
  margin: 0; font-size: 0.7rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.meta__grid {
  margin: 0;
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 6px;
}
.meta__grid dt {
  font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.05em;
  color: rgba(var(--v-theme-on-surface), 0.45);
}
.meta__grid dd {
  margin: 1px 0 0; font-family: var(--v-font-family-monospace, monospace);
  font-size: 0.74rem; color: rgba(var(--v-theme-on-surface), 0.85);
  word-break: break-word;
}
</style>
