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

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useBUDStore } from '@/stores/bud'
import type { CodeReviewRepoStatus, CodeReviewRunStatus } from '@/types'
import {
  CODE_REVIEW_OVERRIDE_REASON_MIN,
  CODE_REVIEW_OVERRIDE_REASON_MAX,
} from '@/types'

const props = defineProps<{
  budId: string
}>()

const emit = defineEmits<{
  (e: 'transitioned'): void
}>()

const budStore = useBUDStore()

const repos = ref<CodeReviewRepoStatus[]>([])
const lastRunStatus = ref<CodeReviewRunStatus>('never_run')
const lastRunMessage = ref<string | null>(null)
const loading = ref(false)

// Only surfaces parse_failed / failed states. The other states (running,
// ok, never_run) communicate via the existing per-repo PR list and the
// agent-running indicators elsewhere on the BUD page — a banner for
// "ok" or "running" would be noisy duplication.
const showRunBanner = computed(
  () => lastRunStatus.value === 'parse_failed' || lastRunStatus.value === 'failed',
)

// Override dialog state
const showOverrideDialog = ref(false)
const overrideReason = ref('')
const submitting = ref(false)
const overrideError = ref('')

const reasonIsValid = computed(() => {
  const trimmed = overrideReason.value.trim()
  return (
    trimmed.length >= CODE_REVIEW_OVERRIDE_REASON_MIN
    && trimmed.length <= CODE_REVIEW_OVERRIDE_REASON_MAX
  )
})

const allMerged = computed(() =>
  repos.value.length > 0 && repos.value.every(r => r.pr_state === 'merged'),
)

async function loadStatus(): Promise<void> {
  loading.value = true
  const data = await budStore.fetchCodeReviewStatus(props.budId)
  repos.value = data.repos
  lastRunStatus.value = data.last_run_status
  lastRunMessage.value = data.last_run_message
  loading.value = false
}

onMounted(loadStatus)
watch(() => props.budId, loadStatus)

function openOverrideDialog(): void {
  overrideReason.value = ''
  overrideError.value = ''
  showOverrideDialog.value = true
}

async function submitOverride(): Promise<void> {
  if (!reasonIsValid.value || submitting.value) return
  submitting.value = true
  overrideError.value = ''
  const result = await budStore.overrideCodeReview(props.budId, overrideReason.value.trim())
  submitting.value = false
  if (result) {
    showOverrideDialog.value = false
    emit('transitioned')
  } else {
    overrideError.value = budStore.error || 'Failed to override code review'
  }
}

// PR-row helpers below take the whole ``CodeReviewRepoStatus`` (not just
// ``pr_state``) because the "all threads resolved" signal — derived from
// ``comment_count`` (unresolved) vs ``total_comment_count`` — modifies the
// pill copy and colour for ``open`` PRs only: the user has finished the
// review-thread back-and-forth but the PR still needs a Merge click.

function isAwaitingMerge(repo: CodeReviewRepoStatus): boolean {
  return (
    repo.pr_state === 'open' &&
    repo.total_comment_count > 0 &&
    repo.comment_count === 0
  )
}

function stateColor(repo: CodeReviewRepoStatus): string {
  if (isAwaitingMerge(repo)) return 'success'
  switch (repo.pr_state) {
    case 'merged': return 'success'
    case 'open': return 'info'
    case 'closed': return 'grey'
    case 'not_raised': return 'warning'
  }
}

function stateIcon(repo: CodeReviewRepoStatus): string {
  if (isAwaitingMerge(repo)) return 'mdi-check-circle-outline'
  switch (repo.pr_state) {
    case 'merged': return 'mdi-source-merge'
    case 'open': return 'mdi-source-pull'
    case 'closed': return 'mdi-source-branch-remove'
    case 'not_raised': return 'mdi-circle-outline'
  }
}

function stateLabel(repo: CodeReviewRepoStatus): string {
  if (isAwaitingMerge(repo)) return 'Resolved · awaiting merge'
  switch (repo.pr_state) {
    case 'merged': return 'Merged'
    case 'open': return 'Open'
    case 'closed': return 'Closed'
    case 'not_raised': return 'No PR'
  }
}

function commentBadgeTooltip(repo: CodeReviewRepoStatus): string {
  if (repo.total_comment_count === 0) return ''
  const resolved = repo.resolved_comment_count
  const total = repo.total_comment_count
  return `${repo.comment_count} unresolved · ${resolved} of ${total} resolved`
}
</script>

<template>
  <div class="pa-4">
    <!-- Header + hint -->
    <div class="d-flex align-center mb-3 ga-2">
      <v-icon size="18" class="mr-1">mdi-source-pull</v-icon>
      <span class="text-subtitle-1 font-weight-medium">Code Review</span>
      <v-spacer />
      <v-btn
        v-if="!loading && repos.length > 0 && !allMerged"
        variant="outlined"
        size="small"
        prepend-icon="mdi-fast-forward"
        color="warning"
        @click="openOverrideDialog"
      >
        Override to QA
      </v-btn>
    </div>

    <div class="text-body-2 text-medium-emphasis mb-3">
      <template v-if="loading">Loading PR status…</template>
      <template v-else-if="repos.length === 0">
        No impacted repos for this BUD. Use <strong>Override to QA</strong> if this is intentional.
      </template>
      <template v-else-if="allMerged">
        All PRs merged. This BUD will auto-advance to QA shortly.
      </template>
      <template v-else>
        Review and merge each impacted repo's PR on GitHub to progress to QA,
        or use <strong>Override to QA</strong> with a reason if merges don't apply
        (docs-only changes, manual merges, etc.).
      </template>
    </div>

    <!-- Last-run failure banner — only shown when the agent task itself
         failed or its output was unparseable. The typed message comes
         from the backend (bud_code_review_status._PARSE_FAILURE_MESSAGES)
         so the user sees a *specific* fix hint, not generic prose. -->
    <v-alert
      v-if="showRunBanner && lastRunMessage"
      type="error"
      variant="tonal"
      density="compact"
      class="mb-3"
      icon="mdi-alert-circle-outline"
    >
      {{ lastRunMessage }}
    </v-alert>

    <!-- Per-repo status list -->
    <v-card v-if="repos.length > 0" variant="outlined" rounded="lg">
      <v-list density="compact" class="py-0">
        <v-list-item
          v-for="repo in repos"
          :key="repo.repo_id"
          :href="repo.pr_url || undefined"
          :target="repo.pr_url ? '_blank' : undefined"
          :disabled="!repo.pr_url"
          class="py-2"
        >
          <template #prepend>
            <v-icon :color="stateColor(repo)" size="small" class="mr-2">
              {{ stateIcon(repo) }}
            </v-icon>
          </template>

          <v-list-item-title class="text-body-2 font-weight-medium">
            {{ repo.repo_name }}
            <span v-if="repo.pr_number" class="text-medium-emphasis ml-1">
              #{{ repo.pr_number }}
            </span>
          </v-list-item-title>

          <template #append>
            <v-chip
              size="x-small"
              :color="stateColor(repo)"
              variant="tonal"
              class="mr-2"
            >
              {{ stateLabel(repo) }}
            </v-chip>
            <v-chip
              v-if="repo.comment_count > 0"
              size="x-small"
              variant="tonal"
              class="mr-2"
              prepend-icon="mdi-comment-text-outline"
              :title="commentBadgeTooltip(repo)"
            >
              {{ repo.comment_count }}
            </v-chip>
            <v-icon v-if="repo.pr_url" size="x-small">mdi-open-in-new</v-icon>
          </template>
        </v-list-item>
      </v-list>
    </v-card>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mt-2" />

    <!-- Override dialog -->
    <v-dialog v-model="showOverrideDialog" max-width="520" persistent>
      <v-card class="pa-2">
        <v-card-title class="text-h6 pb-1">Override code review</v-card-title>
        <v-card-text class="pb-2">
          <p class="text-body-2 text-medium-emphasis mb-3">
            This will skip the PR-merge requirement and move the BUD straight to QA.
            The reason will be recorded in the timeline for audit.
          </p>
          <v-textarea
            v-model="overrideReason"
            variant="outlined"
            density="compact"
            label="Reason (required)"
            rows="3"
            :counter="CODE_REVIEW_OVERRIDE_REASON_MAX"
            :rules="[
              v => !!v?.trim() || 'Reason is required',
              v => (v?.trim().length ?? 0) >= CODE_REVIEW_OVERRIDE_REASON_MIN || `Reason must be at least ${CODE_REVIEW_OVERRIDE_REASON_MIN} characters`,
              v => (v?.length ?? 0) <= CODE_REVIEW_OVERRIDE_REASON_MAX || `Reason must be at most ${CODE_REVIEW_OVERRIDE_REASON_MAX} characters`,
            ]"
            placeholder="e.g. Docs-only change — no PR required; or: merged via hotfix process"
            :disabled="submitting"
          />
          <v-alert
            v-if="overrideError"
            type="error"
            variant="tonal"
            density="compact"
            class="mt-2"
          >
            {{ overrideError }}
          </v-alert>
        </v-card-text>
        <v-card-actions class="px-4 pb-3 pt-0">
          <v-spacer />
          <v-btn variant="text" size="small" :disabled="submitting" @click="showOverrideDialog = false">
            Cancel
          </v-btn>
          <v-btn
            color="warning"
            variant="flat"
            size="small"
            class="ml-2"
            :disabled="!reasonIsValid || submitting"
            :loading="submitting"
            @click="submitOverride"
          >
            Override & Push to QA
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>
