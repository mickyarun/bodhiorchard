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

<template>
  <div>
    <!-- Sticky last-phase-failure banner. Surfaces the most recent
         unresolved `skill_failed` event for this BUD (e.g. pert_estimator
         timeout, server-restart recovery). Dismiss persists server-side
         so the banner stays gone across refreshes. Using an explicit
         close button (not v-alert's `closable`) so the click goes
         straight to our handler — `closable` toggles v-alert's internal
         modelValue too, which can race with the v-if condition. -->
    <v-alert
      v-if="bud.last_phase_failure"
      type="error"
      variant="tonal"
      class="mx-12 mb-3"
    >
      <div class="d-flex align-start ga-2">
        <div class="flex-grow-1">
          <div class="text-body-2 font-weight-medium">
            {{ phaseFailureTitle }}
          </div>
          <div v-if="bud.last_phase_failure.message" class="text-body-2 mt-1">
            {{ bud.last_phase_failure.message }}
          </div>
        </div>
        <v-btn
          variant="text"
          size="small"
          icon="mdi-close"
          :loading="dismissing"
          aria-label="Dismiss failure"
          @click="handleDismissPhaseFailure"
        />
      </div>
    </v-alert>

    <!-- Reassignment Button (development phase, current assignee only) -->
    <v-alert
      v-if="bud.status === 'development' && isCurrentAssignee"
      type="warning"
      variant="tonal"
      class="mx-12 mb-3"
    >
      <div class="d-flex align-center ga-2">
        <div class="flex-grow-1">
          Need to hand this off? Request reassignment to another developer.
        </div>
        <v-btn variant="tonal" size="small" @click="showReassignDialog = true">
          <v-icon start size="16">mdi-swap-horizontal</v-icon>
          Request Reassignment
        </v-btn>
      </div>
    </v-alert>


    <!-- Reassignment dialog -->
    <v-dialog v-model="showReassignDialog" max-width="440">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 mb-2">Request Reassignment</div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          Explain why you'd like to hand off this BUD to another developer.
        </div>
        <v-textarea
          v-model="reassignReason"
          variant="outlined"
          label="Reason"
          rows="3"
          counter="5000"
          :rules="[v => !!v?.trim() || 'Reason is required']"
        />
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="showReassignDialog = false">Cancel</v-btn>
          <v-btn color="warning" variant="flat" :disabled="!reassignReason?.trim()" @click="handleReassignment">
            Request Reassignment
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { useJobSocket } from '@/composables/useJobSocket'
import { subscribe, unsubscribe } from '@/services/socket'
import { friendlyAgentError } from '@/types/agentErrors'
import type { BUDDocument } from '@/types'

const props = defineProps<{
  bud: BUDDocument
  canApprove: boolean
  isCurrentAssignee: boolean
}>()

const emit = defineEmits<{
  (e: 'reload-timeline'): void
}>()

const budStore = useBUDStore()
const { startTracking } = useJobSocket()

// Reassignment state
const showReassignDialog = ref(false)
const reassignReason = ref('')

// Unified agent task tracking (replaces per-type PRD/tech arch/code review refs)
const agentName = ref('')
const taskGenerating = ref(false)
const taskStatusMessage = ref('')

// Synthetic skill slugs published by the backend services.
// agent_activity:{org_id} envelopes use these as `skill_slug`.
const PHASE_ASSIGNER_SLUG = 'phase_assigner'
const PERT_ESTIMATOR_SLUG = 'pert_estimator'

const AGENT_CONFIG: Record<string, { name: string; label: string }> = {
  bud: { name: 'PM Agent', label: 'Writing requirements...' },
  design: { name: 'Designer Agent', label: 'Generating wireframes...' },
  tech_arch: { name: 'Tech Architect Agent', label: 'Generating tech spec...' },
  code_review: { name: 'Code Review Agent', label: 'Reviewing code...' },
  testing: { name: 'QA Agent', label: 'Generating test cases...' },
  development: { name: 'Development Lead', label: 'Setting up the development phase...' },
  [PHASE_ASSIGNER_SLUG]: { name: 'Assignment', label: 'Assigning role…' },
  [PERT_ESTIMATOR_SLUG]: { name: 'Estimator', label: 'Re-estimating phase dates…' },
}

// Phase progress counter — increments on every `skill_invoked`, decrements
// on every `skill_completed` / `skill_failed`. The banner stays visible
// while > 0 so the chain (assignment → todo → estimation) shows as a
// single continuous "AI working…" state instead of flickering between
// stages. A watchdog clears it after 5 min of silence to avoid stuck UI.
const inFlightCount = ref(0)
const phaseMessage = ref('')
const phaseError = ref('')
let watchdogTimer: ReturnType<typeof setTimeout> | null = null
const WATCHDOG_MS = 5 * 60 * 1000

// Subscription bookkeeping so re-subscribing or unmounting cleans up cleanly.
let currentActivityTopic: string | null = null
let currentActivityHandler: ((data: unknown) => void) | null = null
let currentActivityBudId: string | null = null

const phaseInFlight = computed(() => inFlightCount.value > 0)
const agentGenerating = computed(() => taskGenerating.value || phaseInFlight.value)
const agentStatusMessage = computed(() => {
  if (phaseInFlight.value && phaseMessage.value) return phaseMessage.value
  return taskStatusMessage.value
})

async function handleReassignment(): Promise<void> {
  if (!reassignReason.value.trim()) return
  await budStore.requestReassignment(props.bud.id, reassignReason.value)
  showReassignDialog.value = false
  reassignReason.value = ''
}

const phaseFailureTitle = computed(() => {
  const f = props.bud.last_phase_failure
  if (!f) return ''
  const friendly = AGENT_CONFIG[f.skill_slug]?.name
  return friendly ? `${friendly} failed` : 'Last agent run failed'
})

// Local "request in flight" flag so the dismiss button shows a spinner
// + can't double-fire. The store action itself is idempotent on the
// server (stamping ``phase_failure_acknowledged_at`` is set-to-now),
// but a spinner gives the user feedback that the click landed.
const dismissing = ref(false)

async function handleDismissPhaseFailure(): Promise<void> {
  if (dismissing.value) return
  dismissing.value = true
  try {
    await budStore.dismissPhaseFailure(props.bud.id)
  } finally {
    dismissing.value = false
  }
}

// Authoritative-server-state override. When `bud.last_phase_failure` is
// populated, the server has definitively recorded that a worker
// terminated (success or failure of a later attempt clears it on the
// query side). The live in-flight counter is best-effort over WS — if
// its decrement event was missed (dropped socket, race), the counter
// would otherwise stay >0 forever and the "AI working…" banner would
// stick alongside the sticky failure banner. Force the counter to 0
// whenever the server signals a fresh failure.
watch(
  () => props.bud.last_phase_failure,
  (failure) => {
    if (failure) {
      inFlightCount.value = 0
      phaseMessage.value = ''
      agentName.value = ''
    }
  },
  { immediate: true },
)

function trackAgentTask(task: { job_id: string | null; task_type: string; status: string }): void {
  if (!task.job_id) return
  taskGenerating.value = true
  agentName.value = AGENT_CONFIG[task.task_type]?.name || 'AI Agent'
  taskStatusMessage.value = AGENT_CONFIG[task.task_type]?.label || 'Processing...'
  startTracking(task.job_id, {
    onProgress(s) {
      taskStatusMessage.value = s.statusMessage || AGENT_CONFIG[task.task_type]?.label || 'Processing...'
    },
    async onComplete() {
      taskGenerating.value = false
      taskStatusMessage.value = ''
      agentName.value = ''
      await budStore.fetchBUD(props.bud.id)
      emit('reload-timeline')
    },
    async onError(err, errorCode) {
      taskGenerating.value = false
      taskStatusMessage.value = friendlyAgentError(errorCode, err).headline
      agentName.value = ''
      // Refetch so bud.active_agent_task reflects the failed status —
      // the unified top banner and any per-tab consumers read from
      // that field and would otherwise stay stuck on the stale
      // "running" state until the next page load.
      await budStore.fetchBUD(props.bud.id)
      emit('reload-timeline')
    },
  })
}

interface AgentActivityEnvelope {
  event_type?: string
  skill_slug?: string
  message?: string | null
  bud_id?: string | null
  metadata?: Record<string, unknown> | null
}

function armWatchdog(): void {
  if (watchdogTimer) clearTimeout(watchdogTimer)
  watchdogTimer = setTimeout(() => {
    inFlightCount.value = 0
    phaseMessage.value = ''
  }, WATCHDOG_MS)
}

function clearWatchdog(): void {
  if (watchdogTimer) {
    clearTimeout(watchdogTimer)
    watchdogTimer = null
  }
}

function trackAgentActivity(orgId: string, budId: string): void {
  if (!orgId || !budId) return
  if (currentActivityBudId === budId && currentActivityTopic) return

  stopAgentActivity()

  // Re-attach after navigation: if the BUD payload already says a phase
  // worker is in flight, seed the counter so the banner shows up *now*
  // (the WS subscriber alone would only fire on FUTURE events, missing
  // the current stage entirely). On the next `skill_completed` we
  // decrement back to 0 and clean up; on the next `skill_invoked` we
  // bump back up — both branches behave correctly regardless of the
  // seed.
  const seeded = props.bud.active_phase_worker
  if (seeded) {
    inFlightCount.value = 1
    phaseMessage.value = seeded.message
      || AGENT_CONFIG[seeded.skill_slug]?.label
      || 'AI working…'
    agentName.value = AGENT_CONFIG[seeded.skill_slug]?.name || 'AI Agent'
    armWatchdog()
  }

  const topic = `agent_activity:${orgId}`
  const handler = (raw: unknown): void => {
    const env = raw as AgentActivityEnvelope | null
    if (!env || env.bud_id !== budId) return
    const slug = env.skill_slug || ''
    const label = AGENT_CONFIG[slug]?.label
    const friendly = AGENT_CONFIG[slug]?.name

    if (env.event_type === 'skill_invoked') {
      inFlightCount.value += 1
      phaseMessage.value = env.message || label || 'AI working…'
      if (friendly) agentName.value = friendly
      phaseError.value = ''
      armWatchdog()
      return
    }

    if (env.event_type === 'skill_completed' || env.event_type === 'skill_failed') {
      inFlightCount.value = Math.max(0, inFlightCount.value - 1)
      if (env.event_type === 'skill_failed') {
        phaseError.value = env.message || 'Agent step failed'
        phaseMessage.value = phaseError.value
      } else if (inFlightCount.value > 0) {
        phaseMessage.value = env.message || phaseMessage.value
      }
      if (inFlightCount.value === 0) {
        clearWatchdog()
        phaseMessage.value = ''
        agentName.value = ''
        void budStore.fetchBUD(budId)
        emit('reload-timeline')
      } else {
        armWatchdog()
      }
    }
  }

  subscribe(topic, handler)
  currentActivityTopic = topic
  currentActivityHandler = handler
  currentActivityBudId = budId
  // No reconnect-refetch needed: `bud.last_phase_failure` carries the
  // durable failure state across restarts/missed events. The next
  // page-level fetchBUD (mount, visibility, manual nav) surfaces it.
}


function stopAgentActivity(): void {
  if (currentActivityTopic && currentActivityHandler) {
    unsubscribe(currentActivityTopic, currentActivityHandler)
  }
  currentActivityTopic = null
  currentActivityHandler = null
  currentActivityBudId = null
  clearWatchdog()
}

defineExpose({
  agentGenerating,
  agentName,
  agentStatusMessage,
  phaseInFlight,
  phaseError,
  trackAgentTask,
  trackAgentActivity,
  stopAgentActivity,
})
</script>
