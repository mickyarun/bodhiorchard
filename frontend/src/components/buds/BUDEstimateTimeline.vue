<template>
  <div v-if="estimates && estimates.phases.length" class="estimate-timeline">
    <!-- Forecast Header -->
    <div class="forecast-header d-flex align-center justify-space-between mb-3">
      <div class="d-flex align-center ga-2">
        <v-icon icon="mdi-chart-timeline-variant" size="20" color="primary" />
        <span class="text-subtitle-2 font-weight-medium">Go-live Forecast</span>
      </div>
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-refresh"
        :loading="recalculating"
        @click="$emit('recalculate')"
      >
        Recalculate
      </v-btn>
    </div>

    <!-- P50 / P70 / P85 range bar -->
    <div v-if="estimates.prod_p50" class="range-bar mb-4">
      <div class="range-track">
        <div class="range-fill" :style="rangeFillStyle" />
        <div
          v-for="point in percentilePoints"
          :key="point.label"
          class="range-dot"
          :style="{ left: point.position + '%' }"
          :class="{ 'range-dot--primary': point.label === 'P70' }"
        >
          <div class="range-label text-caption">
            <strong>{{ point.label }}</strong>: {{ formatDate(point.date) }}
          </div>
        </div>
      </div>
      <div class="d-flex justify-space-between mt-1">
        <span class="text-caption text-medium-emphasis">optimistic</span>
        <span class="text-caption text-medium-emphasis">safe to promise</span>
      </div>
      <!-- Commit date = prod-P50 + project buffer (Critical Chain). One
           date stakeholders can rely on, distinct from the per-phase
           medians which are deliberately tight. -->
      <div v-if="estimates.commit_date" class="commit-date mt-2">
        <strong>Commit:</strong> {{ formatDate(estimates.commit_date) }}
        <span v-if="estimates.project_buffer_days" class="text-caption text-medium-emphasis ml-1">
          (P50 + {{ formatBufferDays(estimates.project_buffer_days) }} buffer)
        </span>
      </div>
    </div>

    <!-- Complexity + meta row -->
    <div class="d-flex align-center ga-3 mb-4">
      <div v-if="estimates.complexity" class="d-flex align-center ga-1">
        <span class="text-caption text-medium-emphasis">Complexity:</span>
        <span v-for="i in 5" :key="i" class="complexity-dot" :class="i <= estimates.complexity ? 'filled' : 'empty'" />
        <span class="text-caption ml-1">{{ estimates.complexity }}/5</span>
      </div>
      <v-chip v-if="estimates.trigger" size="x-small" variant="tonal" color="primary">
        {{ estimates.trigger }}
      </v-chip>
      <span v-if="estimates.generated_at" class="text-caption text-medium-emphasis">
        Updated {{ timeAgo(estimates.generated_at) }}
      </span>
    </div>

    <!-- Phase stepper. Per-phase dates render the median (P50) per
         Critical Chain — the safety margin is aggregated into the
         buffer pill at the end, not padded into every phase. -->
    <div class="phase-stepper">
      <div
        v-for="(phase, index) in sortedPhases"
        :key="phase.phase"
        class="phase-step"
        :class="{
          'phase-step--done': phaseIndex(phase.phase) < currentPhaseIndex,
          'phase-step--active': phase.phase === currentPhase,
          'phase-step--override': phase.source === 'override',
        }"
        @click="$emit('override-phase', phase.phase)"
      >
        <div class="phase-dot" />
        <div
          v-if="index < sortedPhases.length - 1 || hasBuffer"
          class="phase-connector"
        />
        <div class="phase-info">
          <div class="text-caption font-weight-medium">{{ phaseLabel(phase.phase) }}</div>
          <div class="text-caption" :class="deadlineClass(phase.p50_date)">
            {{ formatDate(phase.p50_date || phase.estimated_completion) }}
          </div>
          <div v-if="phase.source === 'override'" class="text-caption text-warning">
            overridden
          </div>
        </div>
      </div>
      <!-- Project buffer pill — only when the backend supplied a
           non-zero buffer (older snapshots or empty phase lists hide
           it cleanly, no broken layout). -->
      <div v-if="hasBuffer" class="phase-step phase-step--buffer">
        <div class="phase-dot phase-dot--buffer" />
        <div class="phase-info">
          <div class="text-caption font-weight-medium">Buffer</div>
          <div class="text-caption text-medium-emphasis">
            {{ formatBufferDays(estimates.project_buffer_days) }}
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Empty state -->
  <div v-else-if="!loading" class="text-caption text-medium-emphasis text-center pa-4">
    No estimates yet
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { BUDEstimates } from '@/types'
import { BUD_STATUS_ORDER, BUD_STATUS_LABELS } from '@/types'
import type { BUDStatus } from '@/types'

const props = defineProps<{
  estimates: BUDEstimates | null
  currentPhase: string
  loading?: boolean
  recalculating?: boolean
}>()

defineEmits<{
  'recalculate': []
  'override-phase': [phase: string]
}>()

const sortedPhases = computed(() =>
  [...(props.estimates?.phases ?? [])].sort(
    (a, b) =>
      BUD_STATUS_ORDER.indexOf(a.phase as BUDStatus) -
      BUD_STATUS_ORDER.indexOf(b.phase as BUDStatus),
  ),
)

const currentPhaseIndex = computed(() =>
  BUD_STATUS_ORDER.indexOf(props.currentPhase as BUDStatus),
)

function phaseIndex(phase: string): number {
  return BUD_STATUS_ORDER.indexOf(phase as BUDStatus)
}

function phaseLabel(phase: string): string {
  return BUD_STATUS_LABELS[phase as BUDStatus] ?? phase
}

const percentilePoints = computed(() => {
  if (!props.estimates?.prod_p50) return []
  return [
    { label: 'P50', date: props.estimates.prod_p50, position: 15 },
    { label: 'P70', date: props.estimates.prod_p70, position: 50 },
    { label: 'P85', date: props.estimates.prod_p85, position: 85 },
  ]
})

const rangeFillStyle = computed(() => ({
  left: '15%',
  width: '70%',
}))

function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

function deadlineClass(dateStr: string | null | undefined): string {
  if (!dateStr) return 'text-medium-emphasis'
  const days = (new Date(dateStr).getTime() - Date.now()) / 86400000
  if (days < 0) return 'text-error'
  if (days < 2) return 'text-warning'
  return 'text-medium-emphasis'
}

// Hide the Buffer pill cleanly when the backend either didn't supply
// the field (pre-Phase-D snapshot) or computed it as zero (no
// remaining variance to absorb).
const hasBuffer = computed(
  () =>
    !!props.estimates?.project_buffer_days &&
    props.estimates.project_buffer_days > 0,
)

function formatBufferDays(days: number | null | undefined): string {
  if (!days) return '0d'
  // Sub-day buffers round to one decimal; whole-day buffers stay clean.
  return days < 1 ? `${days.toFixed(1)}d` : `${Math.round(days)}d`
}
</script>

<style scoped>
.estimate-timeline {
  padding: 12px 16px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
}

.range-track {
  position: relative;
  height: 4px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
  margin: 24px 0 4px;
}

.range-fill {
  position: absolute;
  height: 100%;
  background: rgb(var(--v-theme-primary));
  opacity: 0.3;
  border-radius: 2px;
}

.range-dot {
  position: absolute;
  top: -4px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.3);
  transform: translateX(-50%);
}

.range-dot--primary {
  background: rgb(var(--v-theme-primary));
  width: 14px;
  height: 14px;
  top: -5px;
}

.range-label {
  position: absolute;
  top: -20px;
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
}

.complexity-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.complexity-dot.filled {
  background: rgb(var(--v-theme-primary));
}

.complexity-dot.empty {
  background: rgba(255, 255, 255, 0.12);
}

.phase-stepper {
  display: flex;
  overflow-x: auto;
  gap: 0;
}

.phase-step {
  position: relative;
  flex: 1;
  min-width: 80px;
  text-align: center;
  cursor: pointer;
  padding: 8px 4px;
  border-radius: 4px;
  transition: background 0.15s;
}

.phase-step:hover {
  background: rgba(255, 255, 255, 0.04);
}

.phase-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  margin: 0 auto 4px;
}

.phase-step--done .phase-dot {
  background: rgb(var(--v-theme-success));
}

.phase-step--active .phase-dot {
  background: rgb(var(--v-theme-primary));
  box-shadow: 0 0 0 3px rgba(var(--v-theme-primary), 0.3);
}

.phase-step--override .phase-dot {
  background: rgb(var(--v-theme-warning));
}

.phase-connector {
  position: absolute;
  top: 12px;
  left: 50%;
  width: 100%;
  height: 2px;
  background: rgba(255, 255, 255, 0.08);
}

.phase-step--done .phase-connector {
  background: rgb(var(--v-theme-success));
  opacity: 0.4;
}

/* Project-buffer pill (Critical Chain) — visually distinct from
   regular phases so stakeholders read it as "shared safety margin"
   rather than another step in the lifecycle. */
.phase-step--buffer {
  cursor: default;
  flex: 0 0 auto;
  min-width: 70px;
}

.phase-step--buffer:hover {
  background: transparent;
}

.phase-dot--buffer {
  background: rgb(var(--v-theme-warning));
  opacity: 0.6;
  border: 1px dashed rgba(255, 255, 255, 0.4);
}

.commit-date {
  font-size: 0.875rem;
  text-align: right;
  color: rgba(255, 255, 255, 0.85);
}
</style>
