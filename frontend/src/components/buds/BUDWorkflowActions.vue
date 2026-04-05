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

    <!-- Repo Confirmation Dialog (for code_review transition) -->
    <v-dialog v-model="showRepoConfirmDialog" max-width="480">
      <v-card class="pa-2">
        <v-card-title class="text-h6 pb-1">Confirm Repos for Code Review</v-card-title>
        <v-card-text class="pb-2">
          <p class="text-body-2 text-medium-emphasis mb-3">Select which repositories should be included in the code review:</p>
          <v-list density="compact" class="py-0">
            <v-list-item v-for="repo in commitRepos" :key="repo.repoPath" class="px-0">
              <template #prepend>
                <v-checkbox-btn v-model="repo.checked" density="compact" color="primary" />
              </template>
              <v-list-item-title class="text-body-2">{{ repo.repoName }}</v-list-item-title>
              <v-list-item-subtitle class="text-caption">{{ repo.commitCount }} commit{{ repo.commitCount !== 1 ? 's' : '' }}</v-list-item-subtitle>
            </v-list-item>
          </v-list>
          <v-alert v-if="commitRepos.length === 0" type="warning" variant="tonal" density="compact" class="mt-2">
            No commits found for this BUD. You can still proceed but the review will have no code changes to analyze.
          </v-alert>
          <v-text-field
            v-if="commitRepos.some(r => !r.checked)"
            v-model="excludeReason"
            label="Reason for excluding repos"
            variant="outlined"
            density="compact"
            class="mt-3"
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-3 pt-0">
          <v-spacer />
          <v-btn variant="text" size="small" @click="showRepoConfirmDialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" size="small" class="ml-2" @click="confirmCodeReviewTransition">
            Start Code Review
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { useAuthStore } from '@/stores/auth'
import { useJobSocket } from '@/composables/useJobSocket'
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
const authStore = useAuthStore()
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

// Code review UI state
const showRepoConfirmDialog = ref(false)
const commitRepos = ref<{ repoPath: string; repoName: string; commitCount: number; checked: boolean }[]>([])
const excludeReason = ref('')

async function handleReassignment(): Promise<void> {
  if (!reassignReason.value.trim()) return
  await budStore.requestReassignment(props.bud.id, reassignReason.value)
  showReassignDialog.value = false
  reassignReason.value = ''
}

async function showCodeReviewConfirmation(): Promise<void> {
  try {
    const resp = await fetch(`/api/v1/buds/${props.bud.id}/commits/repos`, {
      headers: { 'Authorization': `Bearer ${authStore.token}` },
    })
    if (resp.ok) {
      const repos = await resp.json()
      commitRepos.value = repos.map((r: { repo_path: string; repo_name: string; commit_count: number }) => ({
        repoPath: r.repo_path,
        repoName: r.repo_name,
        commitCount: r.commit_count,
        checked: true,
      }))
    } else {
      console.error('[CodeReview] commits/repos failed:', resp.status, await resp.text())
      commitRepos.value = []
    }
  } catch (err) {
    console.error('[CodeReview] commits/repos error:', err)
    commitRepos.value = []
  }
  showRepoConfirmDialog.value = true
}

async function confirmCodeReviewTransition(): Promise<void> {
  showRepoConfirmDialog.value = false

  const confirmedRepos = commitRepos.value
    .filter(r => r.checked)
    .map(r => ({
      repo_path: r.repoPath,
      repo_name: r.repoName,
    }))
  const excludedRepos = commitRepos.value
    .filter(r => !r.checked)
    .map(r => ({
      repo_path: r.repoPath,
      repo_name: r.repoName,
      reason: excludeReason.value || 'Excluded by user',
    }))

  const meta = { ...(props.bud.metadata || {}), confirmed_repos: confirmedRepos, excluded_repos: excludedRepos }
  await budStore.updateBUD(props.bud.id, { metadata: meta, status: 'code_review' } as never)

  // After status update, the backend creates the agent task automatically.
  // The frontend picks it up on the next fetchBUD via active_agent_task.
  await budStore.fetchBUD(props.bud.id)
  emit('reload-timeline')
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
    async onError(err) {
      agentGenerating.value = false
      agentStatusMessage.value = `Failed: ${err}`
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
  showCodeReviewConfirmation,
  trackAgentTask,
})
</script>
