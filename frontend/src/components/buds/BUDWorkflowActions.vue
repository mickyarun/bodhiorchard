<template>
  <div>
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
import { ref } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { useJobSocket } from '@/composables/useJobSocket'
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
const agentGenerating = ref(false)
const agentStatusMessage = ref('')

const AGENT_CONFIG: Record<string, { name: string; label: string }> = {
  bud: { name: 'PM Agent', label: 'Writing requirements...' },
  design: { name: 'Designer Agent', label: 'Generating wireframes...' },
  tech_arch: { name: 'Tech Architect Agent', label: 'Generating tech spec...' },
  code_review: { name: 'Code Review Agent', label: 'Reviewing code...' },
  testing: { name: 'QA Agent', label: 'Generating test cases...' },
}

async function handleReassignment(): Promise<void> {
  if (!reassignReason.value.trim()) return
  await budStore.requestReassignment(props.bud.id, reassignReason.value)
  showReassignDialog.value = false
  reassignReason.value = ''
}

// Unified agent task tracking (replaces per-type trackPrdJobIfActive etc.)
const agentName = ref('')

function trackAgentTask(task: { job_id: string | null; task_type: string; status: string }): void {
  if (!task.job_id) return
  agentGenerating.value = true
  agentName.value = AGENT_CONFIG[task.task_type]?.name || 'AI Agent'
  agentStatusMessage.value = AGENT_CONFIG[task.task_type]?.label || 'Processing...'
  startTracking(task.job_id, {
    onProgress(s) {
      agentStatusMessage.value = s.statusMessage || AGENT_CONFIG[task.task_type]?.label || 'Processing...'
    },
    async onComplete() {
      agentGenerating.value = false
      agentStatusMessage.value = ''
      agentName.value = ''
      await budStore.fetchBUD(props.bud.id)
      emit('reload-timeline')
    },
    async onError(err, errorCode) {
      agentGenerating.value = false
      agentStatusMessage.value = friendlyAgentError(errorCode, err).headline
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

defineExpose({
  agentGenerating,
  agentName,
  agentStatusMessage,
  trackAgentTask,
})
</script>
