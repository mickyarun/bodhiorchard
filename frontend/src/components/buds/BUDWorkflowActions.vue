<template>
  <div>
    <!-- Tech Arch Generating Banner -->
    <v-alert
      v-if="bud.status === 'tech_arch' && techArchGenerating"
      type="info"
      variant="tonal"
      class="mx-12 mb-3"
    >
      <div class="d-flex align-center ga-2">
        <v-progress-circular indeterminate size="18" width="2" class="mr-2" />
        <div class="flex-grow-1">
          <strong>Generating Tech Architecture...</strong>
          <div class="text-caption text-medium-emphasis">{{ techArchStatusMessage || 'Claude is analyzing your requirements and designing the implementation plan...' }}</div>
        </div>
      </div>
    </v-alert>

    <!-- Tech Architecture Approval Bar -->
    <v-alert
      v-if="bud.status === 'tech_arch' && canApprove && !!bud.tech_spec_md && !techArchGenerating"
      type="info"
      variant="tonal"
      class="mx-12 mb-3"
    >
      <div class="d-flex align-center ga-2">
        <div class="flex-grow-1">
          <strong>Tech Architecture Review</strong>
          <span v-if="awaitingManagerApproval"> — Awaiting manager approval</span>
          <span v-else> — Review the tech spec and approve or reject</span>
        </div>
        <v-btn
          color="success"
          variant="flat"
          size="small"
          :loading="approvingTechArch"
          :disabled="approvingTechArch"
          @click="handleApproveTechArch"
        >
          <v-icon start size="16">mdi-check</v-icon>
          Approve
        </v-btn>
        <v-btn
          color="error"
          variant="tonal"
          size="small"
          :disabled="approvingTechArch"
          @click="showRejectDialog = true"
        >
          <v-icon start size="16">mdi-close</v-icon>
          Reject
        </v-btn>
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

    <!-- Code Review Generating Banner -->
    <v-alert
      v-if="bud.status === 'code_review' && codeReviewGenerating"
      type="info"
      variant="tonal"
      class="mx-12 mb-3"
    >
      <div class="d-flex align-center ga-2">
        <v-progress-circular indeterminate size="18" width="2" class="mr-2" />
        <div class="flex-grow-1">
          <strong>Running Code Review...</strong>
          <div class="text-caption text-medium-emphasis">{{ codeReviewStatusMessage || 'Claude is reviewing your code changes...' }}</div>
        </div>
      </div>
    </v-alert>

    <!-- Code Review Comments Panel -->
    <v-card
      v-if="bud.status === 'code_review' && codeReviewComments.length > 0 && !codeReviewGenerating"
      variant="outlined"
      class="mx-12 mb-3"
    >
      <v-card-title class="text-subtitle-1 d-flex align-center">
        <v-icon start size="18">mdi-comment-check-outline</v-icon>
        Code Review Comments ({{ codeReviewComments.length }})
      </v-card-title>
      <v-divider />
      <v-list density="compact">
        <v-list-item
          v-for="(c, idx) in codeReviewComments"
          :key="idx"
          :class="{ 'bg-green-lighten-5': c.status === 'accepted', 'bg-grey-lighten-4': c.status === 'skipped' }"
        >
          <template #prepend>
            <v-icon
              :color="c.severity === 'error' ? 'error' : c.severity === 'warning' ? 'warning' : 'info'"
              size="18"
            >
              {{ c.severity === 'error' ? 'mdi-alert-circle' : c.severity === 'warning' ? 'mdi-alert' : 'mdi-information' }}
            </v-icon>
          </template>
          <v-list-item-title class="text-body-2">
            <code class="text-caption">{{ c.repo }}/{{ c.file }}:{{ c.line }}</code>
            <v-chip v-if="c.deviates_from_spec" size="x-small" color="error" variant="tonal" class="ml-2">Spec Deviation</v-chip>
          </v-list-item-title>
          <v-list-item-subtitle class="text-body-2 mt-1">{{ c.comment }}</v-list-item-subtitle>
          <template #append>
            <div v-if="!c.status || c.status === 'pending'" class="d-flex ga-1">
              <v-btn size="x-small" variant="tonal" color="success" @click="handleReviewComment(idx, 'accepted')">
                Accept
              </v-btn>
              <v-btn size="x-small" variant="tonal" color="grey" @click="handleReviewComment(idx, 'skipped', 'Not applicable')">
                Skip
              </v-btn>
            </div>
            <v-chip v-else size="x-small" :color="c.status === 'accepted' ? 'success' : 'grey'" variant="tonal">
              {{ c.status }}
            </v-chip>
          </template>
        </v-list-item>
      </v-list>
      <v-divider />
      <v-card-actions>
        <v-spacer />
        <v-btn
          color="primary"
          variant="flat"
          size="small"
          :disabled="codeReviewComments.some(c => !c.status || c.status === 'pending')"
          @click="emit('status-change', 'testing')"
        >
          Move to QA
          <v-icon end size="16">mdi-arrow-right</v-icon>
        </v-btn>
      </v-card-actions>
    </v-card>

    <!-- Test Plans (code_review phase) -->
    <v-expansion-panels
      v-if="bud.status === 'code_review' && (automationTestPlan || manualTestPlan) && !codeReviewGenerating"
      variant="accordion"
      class="mx-12 mb-3"
    >
      <v-expansion-panel v-if="automationTestPlan">
        <v-expansion-panel-title>
          <v-icon start size="18">mdi-test-tube</v-icon>
          Automation Test Plan
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="markdown-body" v-html="renderMarkdown(automationTestPlan)" />
        </v-expansion-panel-text>
      </v-expansion-panel>
      <v-expansion-panel v-if="manualTestPlan">
        <v-expansion-panel-title>
          <v-icon start size="18">mdi-clipboard-check-outline</v-icon>
          Manual Test Plan
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="markdown-body" v-html="renderMarkdown(manualTestPlan)" />
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <!-- Reject Tech Arch dialog -->
    <v-dialog v-model="showRejectDialog" max-width="440">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 mb-2">Reject Tech Plan</div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          Provide a reason so the team can revise the plan.
        </div>
        <v-textarea
          v-model="rejectReason"
          variant="outlined"
          label="Reason"
          rows="3"
          counter="5000"
          :rules="[v => !!v?.trim() || 'Reason is required']"
        />
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="showRejectDialog = false">Cancel</v-btn>
          <v-btn color="error" variant="flat" :disabled="!rejectReason?.trim()" @click="handleRejectTechArch">
            Reject
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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
    <v-dialog v-model="showRepoConfirmDialog" max-width="520">
      <v-card>
        <v-card-title>Confirm Repos for Code Review</v-card-title>
        <v-card-text>
          <p class="text-body-2 mb-3">Select which repositories should be included in the code review:</p>
          <v-list density="compact">
            <v-list-item v-for="repo in commitRepos" :key="repo.repoPath">
              <template #prepend>
                <v-checkbox-btn v-model="repo.checked" density="compact" />
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
        <v-card-actions>
          <v-btn variant="text" @click="showRepoConfirmDialog = false">Cancel</v-btn>
          <v-spacer />
          <v-btn color="primary" variant="flat" @click="confirmCodeReviewTransition">
            Start Code Review
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { useAuthStore } from '@/stores/auth'
import { useJobSocket } from '@/composables/useJobSocket'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import type { BUDDocument } from '@/types'

const props = defineProps<{
  bud: BUDDocument
  canApprove: boolean
  isCurrentAssignee: boolean
}>()

const emit = defineEmits<{
  (e: 'status-change', status: string): void
  (e: 'reload-timeline'): void
}>()

const budStore = useBUDStore()
const authStore = useAuthStore()
const { startTracking } = useJobSocket()

// Tech architecture state
const showRejectDialog = ref(false)
const showReassignDialog = ref(false)
const rejectReason = ref('')
const reassignReason = ref('')
const approvingTechArch = ref(false)

// Tech arch generation tracking
const techArchGenerating = ref(false)
const techArchStatusMessage = ref('')

// PRD generation tracking
const prdGenerating = ref(false)
const prdStatusMessage = ref('')

// Code review tracking
const codeReviewGenerating = ref(false)
const codeReviewStatusMessage = ref('')
const showRepoConfirmDialog = ref(false)
const commitRepos = ref<{ repoPath: string; repoName: string; commitCount: number; checked: boolean }[]>([])
const excludeReason = ref('')

interface CodeReviewComment {
  repo: string
  file: string
  line: number
  severity: 'error' | 'warning' | 'suggestion'
  comment: string
  deviates_from_spec: boolean
  status?: 'pending' | 'accepted' | 'skipped'
  skip_reason?: string
}

const awaitingManagerApproval = computed(() => {
  const meta = props.bud?.metadata as Record<string, unknown> | null
  const approval = meta?.tech_arch_approval as Record<string, unknown> | undefined
  return approval?.awaiting_manager === true
})

const codeReviewComments = computed<CodeReviewComment[]>(() => {
  const meta = props.bud?.metadata as Record<string, unknown> | null
  return (meta?.code_review_comments as CodeReviewComment[] | undefined) ?? []
})

const automationTestPlan = computed(() => {
  const meta = props.bud?.metadata as Record<string, unknown> | null
  return (meta?.automation_test_plan_md as string | undefined) ?? ''
})

const manualTestPlan = computed(() => {
  const meta = props.bud?.metadata as Record<string, unknown> | null
  return (meta?.manual_test_plan_md as string | undefined) ?? ''
})

function renderMarkdown(md: string | null): string {
  if (!md) return ''
  const raw = marked.parse(md, { async: false }) as string
  return DOMPurify.sanitize(raw)
}

async function handleApproveTechArch(): Promise<void> {
  approvingTechArch.value = true
  try {
    await budStore.approveTechArch(props.bud.id)
  } finally {
    approvingTechArch.value = false
  }
}

async function handleRejectTechArch(): Promise<void> {
  if (!rejectReason.value.trim()) return
  await budStore.rejectTechArch(props.bud.id, rejectReason.value)
  showRejectDialog.value = false
  rejectReason.value = ''
}

async function handleReassignment(): Promise<void> {
  if (!reassignReason.value.trim()) return
  await budStore.requestReassignment(props.bud.id, reassignReason.value)
  showReassignDialog.value = false
  reassignReason.value = ''
}

async function handleReviewComment(idx: number, action: 'accepted' | 'skipped', reason?: string): Promise<void> {
  const meta = { ...(props.bud.metadata || {}) } as Record<string, unknown>
  const comments = [...(meta.code_review_comments as CodeReviewComment[] || [])]
  if (comments[idx]) {
    comments[idx] = { ...comments[idx], status: action }
    if (reason) comments[idx].skip_reason = reason
    meta.code_review_comments = comments
    await budStore.updateBUD(props.bud.id, { metadata: meta } as never)
  }
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
      commitRepos.value = []
    }
  } catch {
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

  const refreshed = budStore.currentBUD
  const crJobId = (refreshed?.metadata as Record<string, unknown> | null)?.code_review_job_id as string | undefined
  if (crJobId) {
    trackCodeReviewJob(crJobId)
  }

  emit('reload-timeline')
}

function trackCodeReviewJob(jobId: string): void {
  codeReviewGenerating.value = true
  codeReviewStatusMessage.value = 'Starting code review...'
  startTracking(jobId, {
    onProgress(s) {
      codeReviewStatusMessage.value = s.statusMessage || 'Reviewing code...'
    },
    async onComplete() {
      codeReviewGenerating.value = false
      codeReviewStatusMessage.value = ''
      await budStore.fetchBUD(props.bud.id)
    },
    onError(err) {
      codeReviewGenerating.value = false
      codeReviewStatusMessage.value = `Failed: ${err}`
    },
  })
}

function trackPrdJobIfActive(): void {
  const meta = props.bud?.metadata as Record<string, unknown> | null
  const jobId = meta?.prd_job_id as string | undefined
  if (!jobId) return
  prdGenerating.value = true
  startTracking(jobId, {
    onProgress(s) {
      prdStatusMessage.value = s.statusMessage || 'PRD agent is enriching requirements...'
    },
    async onComplete() {
      prdGenerating.value = false
      prdStatusMessage.value = ''
      await budStore.fetchBUD(props.bud.id)
    },
    onError() {
      prdGenerating.value = false
      prdStatusMessage.value = ''
    },
  })
}

function trackTechArchJobIfActive(): void {
  const meta = props.bud?.metadata as Record<string, unknown> | null
  const jobId = meta?.tech_arch_job_id as string | undefined
  if (!jobId) return
  techArchGenerating.value = true
  startTracking(jobId, {
    onProgress(s) {
      techArchStatusMessage.value = s.statusMessage || 'Generating tech architecture...'
    },
    async onComplete() {
      techArchGenerating.value = false
      techArchStatusMessage.value = ''
      await budStore.fetchBUD(props.bud.id)
    },
    onError() {
      techArchGenerating.value = false
      techArchStatusMessage.value = ''
    },
  })
}

function trackCodeReviewJobIfActive(): void {
  const meta = props.bud?.metadata as Record<string, unknown> | null
  const jobId = meta?.code_review_job_id as string | undefined
  if (!jobId) return
  trackCodeReviewJob(jobId)
}

defineExpose({
  prdGenerating,
  prdStatusMessage,
  techArchGenerating,
  codeReviewGenerating,
  showCodeReviewConfirmation,
  trackPrdJobIfActive,
  trackTechArchJobIfActive,
  trackCodeReviewJobIfActive,
})
</script>
