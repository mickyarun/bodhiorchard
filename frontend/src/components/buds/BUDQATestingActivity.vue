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
  <div class="qa-activity">
    <!-- Section header — always visible, always reachable. The ? button
         opens the MCP setup dialog so a tester can find the instructions
         even when activity is already populated by someone else. -->
    <div class="section-header">
      <div class="d-flex align-center ga-2">
        <v-icon icon="mdi-test-tube" size="18" color="purple" />
        <span class="text-subtitle-2 font-weight-medium">QA Automation Activity</span>
        <v-chip
          v-if="hasActivity"
          size="x-small"
          variant="tonal"
          color="purple"
        >
          {{ stats.total_commits }} commit{{ stats.total_commits !== 1 ? 's' : '' }}
        </v-chip>
      </div>
      <v-spacer />
      <v-tooltip text="MCP token setup help" location="top">
        <template #activator="{ props: tipProps }">
          <v-btn
            v-bind="tipProps"
            icon="mdi-help-circle-outline"
            size="small"
            variant="text"
            density="comfortable"
            aria-label="Show MCP token setup instructions"
            @click="setupDialogOpen = true"
          />
        </template>
      </v-tooltip>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="d-flex justify-center py-6">
      <v-progress-circular indeterminate size="20" width="2" color="purple" />
    </div>

    <!-- Empty state — show inline MCP hint -->
    <div v-else-if="!hasActivity && untrackedRepos.length === 0" class="empty-state">
      <v-icon icon="mdi-clipboard-clock-outline" size="36" color="purple" class="mb-2 opacity-40" />
      <div class="text-body-2 text-medium-emphasis mb-3">
        No QA automation activity yet.
      </div>
      <MCPSetupHint purpose="testing" class="mb-3" />
      <v-btn
        variant="outlined"
        size="small"
        prepend-icon="mdi-content-copy"
        @click="copyBranchName"
      >
        Copy Branch Name
      </v-btn>
      <div v-if="branchCopied" class="text-caption text-success mt-2">Copied!</div>
    </div>

    <!-- Has activity -->
    <template v-else>
      <!-- Stats row -->
      <div class="stats-row mb-4">
        <div class="stat-card">
          <v-icon icon="mdi-source-commit" size="18" color="purple" class="mb-1" />
          <div class="stat-value">{{ stats.total_commits }}</div>
          <div class="stat-label">Commits</div>
        </div>
        <div class="stat-card">
          <v-icon icon="mdi-file-multiple" size="18" color="teal" class="mb-1" />
          <div class="stat-value">{{ stats.total_files_changed }}</div>
          <div class="stat-label">Files</div>
        </div>
        <div class="stat-card">
          <v-icon icon="mdi-pulse" size="18" color="blue" class="mb-1" />
          <div class="stat-value">{{ activities.length }}</div>
          <div class="stat-label">Events</div>
        </div>
        <div class="stat-card">
          <v-icon icon="mdi-source-repository" size="18" color="grey" class="mb-1" />
          <div class="stat-value">{{ stats.repos_touched + untrackedRepos.length }}</div>
          <div class="stat-label">Repos</div>
        </div>
      </div>

      <!-- Prompt when events flow but no commits yet -->
      <v-alert
        v-if="stats.total_commits === 0 && activities.length > 0"
        variant="tonal"
        density="compact"
        color="info"
        icon="mdi-information-outline"
        class="mb-4"
      >
        <div class="text-body-2">
          Activity is flowing ({{ activities.length }} event{{ activities.length !== 1 ? 's' : '' }} tracked).
          Commits will appear here once code is committed on a
          <code>bud-{{ String(budNumber || 0).padStart(3, '0') }}/</code> branch.
        </div>
      </v-alert>

      <!-- Untracked repos warning — rendered above contributors so a new
           tester immediately sees the prompt to add their repo. Each row
           is a self-contained card with the path, commit count, and a
           one-click "Add as tracked" CTA. -->
      <div v-if="untrackedRepos.length > 0" class="untracked-section mb-4">
        <div class="text-caption text-medium-emphasis mb-2">
          Untracked repositories
        </div>
        <v-alert
          v-for="repo in untrackedRepos"
          :key="repo.repo_path"
          color="warning"
          variant="tonal"
          density="compact"
          class="untracked-row mb-2"
          icon="mdi-source-repository-multiple"
        >
          <div class="d-flex align-center ga-3">
            <div class="flex-grow-1 min-width-0">
              <div class="text-body-2 font-weight-medium text-truncate">
                {{ repo.name || repo.repo_path }}
              </div>
              <div class="text-caption text-medium-emphasis text-truncate">
                <code>{{ repo.repo_path }}</code> · {{ repo.commit_count }} commit{{ repo.commit_count !== 1 ? 's' : '' }}
              </div>
            </div>
            <v-btn
              size="small"
              variant="flat"
              color="warning"
              prepend-icon="mdi-plus"
              :disabled="addingRepoPath === repo.repo_path"
              @click="confirmAddRepo(repo)"
            >
              Add as tracked
            </v-btn>
          </div>
        </v-alert>
      </div>

      <!-- Tracked repo chips — same pattern as the dev panel -->
      <div v-if="repos.length > 0" class="health-row mb-4">
        <v-chip
          v-for="repo in repos"
          :key="repo.repo_path"
          size="small"
          variant="outlined"
          prepend-icon="mdi-git"
        >
          {{ repo.repo_name }}
        </v-chip>
      </div>

      <!-- Commits by contributor -->
      <div v-if="contributors.length > 0" class="contributors-section">
        <div v-for="dev in contributors" :key="dev.user_id || dev.author_email || 'unknown'" class="contributor-block">
          <div class="contributor-header">
            <v-avatar size="24" color="surface-variant">
              <span class="text-caption font-weight-bold">
                {{ (dev.user_name || dev.author_name || '?')[0].toUpperCase() }}
              </span>
            </v-avatar>
            <span class="text-body-2 font-weight-medium">
              {{ dev.user_name || dev.author_name || dev.author_email || 'Unknown' }}
            </span>
            <span class="text-caption text-medium-emphasis">
              {{ dev.commit_count }} commit{{ dev.commit_count !== 1 ? 's' : '' }}
            </span>
          </div>

          <div class="commit-list">
            <div
              v-for="c in dev.commits"
              :key="c.commit_sha"
              class="commit-entry"
            >
              <div class="commit-header">
                <code class="commit-sha">{{ c.commit_sha.slice(0, 7) }}</code>
                <span class="commit-msg text-body-2">{{ c.commit_message }}</span>
                <span class="text-caption text-medium-emphasis text-no-wrap ml-auto">
                  {{ timeAgo(c.created_at) }}
                </span>
              </div>
              <div v-if="parseFiles(c.files_changed).length > 0" class="commit-files">
                <div
                  v-for="file in parseFiles(c.files_changed)"
                  :key="file"
                  class="file-row"
                >
                  <v-icon
                    :icon="fileIcon(file)"
                    size="12"
                    :color="fileColor(file)"
                    class="mr-1"
                  />
                  <span class="file-name">{{ file }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Activity Timeline — collapsible log of all raw events (sessions,
           prompts, file edits, errors). Matches the dev panel's accordion
           so the two tabs feel consistent. Visible even when there are no
           commits — useful for verifying that tracking is working. -->
      <v-expansion-panels v-if="activities.length > 0" variant="accordion" class="activity-accordion mt-4">
        <v-expansion-panel>
          <v-expansion-panel-title>
            <v-icon icon="mdi-timeline-clock-outline" size="18" class="mr-2 opacity-60" />
            <span class="text-body-2 text-medium-emphasis">Activity Timeline</span>
            <v-chip size="x-small" variant="tonal" class="ml-2">{{ activities.length }}</v-chip>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <div class="activity-log">
              <div v-for="a in activities" :key="a.id" class="activity-log-item">
                <v-icon :icon="eventIcon(a)" size="14" :color="eventColor(a)" class="mr-2 mt-1 flex-shrink-0" />
                <div class="flex-grow-1 min-width-0">
                  <div class="text-body-2 text-truncate">{{ a.message || a.event_type }}</div>
                  <div class="text-caption text-medium-emphasis">
                    {{ a.event_type }}
                    <span v-if="a.actor_name"> &middot; {{ a.actor_name }}</span>
                    &middot; {{ timeAgo(a.created_at) }}
                  </div>
                </div>
              </div>
            </div>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </template>

    <!-- MCP Setup dialog — reuses the same shared component. Always
         reachable via the ? button in the header. -->
    <v-dialog v-model="setupDialogOpen" max-width="520">
      <v-card class="pa-5">
        <div class="d-flex align-center justify-space-between mb-3">
          <div class="text-subtitle-1 font-weight-medium">
            QA automation MCP setup
          </div>
          <v-btn
            icon="mdi-close"
            variant="text"
            size="small"
            density="comfortable"
            @click="setupDialogOpen = false"
          />
        </div>
        <div class="text-body-2 text-medium-emphasis mb-3">
          Configure Claude Code in your QA automation repo so test
          commits flow back to this BUD's testing tab.
        </div>
        <MCPSetupHint purpose="testing" />
      </v-card>
    </v-dialog>

    <!-- Add-as-tracked confirm dialog. Shows the path and the consequences
         (the repo becomes part of the org's tracked set, future commits
         resolve to it normally). On confirm, hits the existing
         settingsStore.addRepo endpoint. -->
    <v-dialog v-model="addRepoDialogOpen" max-width="480">
      <v-card class="pa-5">
        <div class="text-subtitle-1 font-weight-medium mb-3">
          Add as tracked repository?
        </div>
        <div class="text-body-2 mb-2">
          The following repo will be added to your org's tracked
          repositories:
        </div>
        <div class="path-display mb-3">
          <code>{{ pendingRepo?.repo_path }}</code>
        </div>
        <div class="text-caption text-medium-emphasis mb-4">
          Future commits from this path will be linked to the BUD's testing
          tab as a tracked repo. Existing commits ({{ pendingRepo?.commit_count }})
          will be re-grouped on next refresh.
        </div>
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="addRepoDialogOpen = false">
            Cancel
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="addingRepoPath !== ''"
            prepend-icon="mdi-plus"
            @click="executeAddRepo"
          >
            Add Repository
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Snackbar surfaces success / failure of the add-repo action. -->
    <v-snackbar
      v-model="snackbarOpen"
      :color="snackbarColor"
      location="bottom"
      :timeout="4000"
    >
      {{ snackbarMessage }}
      <template #actions>
        <v-btn variant="text" @click="snackbarOpen = false">Dismiss</v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useBudActivity } from '@/composables/useBudActivity'
import { useSettingsStore } from '@/stores/settings'
import { fileColor, fileIcon, parseFiles, timeAgo } from '@/utils/dev-activity-helpers'
import type { DevActivity, UntrackedRepo } from '@/types'
import MCPSetupHint from './MCPSetupHint.vue'

const props = defineProps<{
  budId: string
  budNumber?: number
}>()

// Always filter to qa-role activity. The composable hits the same
// /dev-activity endpoint the dev tab does, just with ?role=qa appended.
const {
  activities,
  contributors,
  repos,
  untrackedRepos,
  stats,
  loading,
  load,
  startListening,
} = useBudActivity(props.budId, { role: 'qa' })

const settingsStore = useSettingsStore()

// ── UI state ──────────────────────────────────────────────────────────

const setupDialogOpen = ref(false)
const addRepoDialogOpen = ref(false)
const pendingRepo = ref<UntrackedRepo | null>(null)
const addingRepoPath = ref('')

const branchCopied = ref(false)

const snackbarOpen = ref(false)
const snackbarMessage = ref('')
const snackbarColor = ref<'success' | 'error'>('success')

// ── Derived state ─────────────────────────────────────────────────────

// hasActivity includes raw events (user_prompt, file_change, etc.) — not
// just commits. A QA tester who started a Claude Code session but hasn't
// committed yet still has activity flowing (sessions, prompts, file edits).
// Showing the section with a "no commits yet" note is better than hiding
// it entirely and making the user think tracking is broken.
const hasActivity = computed(
  () => activities.value.length > 0 || contributors.value.length > 0,
)

// ── Actions ───────────────────────────────────────────────────────────

function confirmAddRepo(repo: UntrackedRepo): void {
  pendingRepo.value = repo
  addRepoDialogOpen.value = true
}

async function executeAddRepo(): Promise<void> {
  if (!pendingRepo.value) return
  const repoPath = pendingRepo.value.repo_path
  addingRepoPath.value = repoPath
  try {
    const ok = await settingsStore.addRepo(repoPath)
    if (ok) {
      snackbarMessage.value = `Added ${pendingRepo.value.name || repoPath} as a tracked repository`
      snackbarColor.value = 'success'
      snackbarOpen.value = true
      addRepoDialogOpen.value = false
      pendingRepo.value = null
      // Refresh the activity stream — the just-added repo should now
      // resolve to a tracked_repositories.id and disappear from the
      // untracked list.
      await load()
    } else {
      // settingsStore.addRepo writes the error message into
      // settingsStore.error via extractApiError; surface it verbatim.
      snackbarMessage.value = settingsStore.error || 'Failed to add repository'
      snackbarColor.value = 'error'
      snackbarOpen.value = true
    }
  } finally {
    addingRepoPath.value = ''
  }
}

async function copyBranchName(): Promise<void> {
  const name = `bud-${String(props.budNumber || 0).padStart(3, '0')}/`
  await navigator.clipboard.writeText(name)
  branchCopied.value = true
  setTimeout(() => {
    branchCopied.value = false
  }, 2000)
}

// ── Activity timeline helpers (mirrors BUDDevelopmentPanel) ───────

function eventIcon(a: DevActivity): string {
  const et = a.event_type || ''
  if (et === 'commit') return 'mdi-source-commit'
  if (et === 'file_change') return 'mdi-file-edit'
  if (et === 'session_start') return 'mdi-play-circle'
  if (et === 'session_end') return 'mdi-stop-circle'
  if (et === 'tool_error' || et === 'api_error') return 'mdi-alert-circle'
  if (et === 'activity_summary') return 'mdi-text-box-check'
  if (et === 'user_prompt') return 'mdi-message-text-outline'
  if (a.status === 'completed') return 'mdi-check-circle'
  if (a.status === 'failed') return 'mdi-alert-circle'
  return 'mdi-information'
}

function eventColor(a: DevActivity): string {
  const et = a.event_type || ''
  if (et === 'tool_error' || et === 'api_error') return 'error'
  if (et === 'commit') return 'purple'
  if (et === 'session_start') return 'success'
  if (et === 'session_end') return 'grey'
  if (et === 'user_prompt') return 'blue'
  if (a.status === 'failed') return 'error'
  if (a.status === 'completed') return 'success'
  return 'info'
}

onMounted(() => {
  load()
  startListening()
})

watch(() => props.budId, () => load())
</script>

<style scoped>
.qa-activity {
  display: flex;
  flex-direction: column;
  margin-bottom: 16px;
}

/* ── Section header ─────────────────────────────────────────────── */

.section-header {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

/* ── Empty state ────────────────────────────────────────────────── */

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 16px;
  text-align: center;
}

/* ── Stats row ──────────────────────────────────────────────────── */

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 8px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
  color: rgba(var(--v-theme-on-surface), 0.92);
}

.stat-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

/* ── Untracked repos ────────────────────────────────────────────── */

.untracked-section {
  display: flex;
  flex-direction: column;
}

.untracked-row :deep(.v-alert__content) {
  width: 100%;
}

.untracked-row code {
  font-size: 11px;
  font-family: ui-monospace, monospace;
}

.path-display {
  padding: 8px 12px;
  background: rgba(var(--v-theme-on-surface), 0.05);
  border-radius: 4px;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  word-break: break-all;
}

/* ── Tracked repo chips ─────────────────────────────────────────── */

.health-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

/* ── Contributors / commits ─────────────────────────────────────── */

.contributors-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.contributor-block {
  display: flex;
  flex-direction: column;
}

.contributor-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.commit-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 32px;
}

.commit-entry {
  border-left: 2px solid rgba(var(--v-theme-on-surface), 0.1);
  padding: 4px 0 4px 12px;
}

.commit-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.commit-sha {
  font-family: ui-monospace, monospace;
  font-size: 11px;
  background: rgba(var(--v-theme-on-surface), 0.08);
  padding: 1px 6px;
  border-radius: 3px;
  color: rgba(var(--v-theme-on-surface), 0.75);
}

.commit-msg {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.commit-files {
  margin-top: 4px;
  padding-left: 8px;
}

.file-row {
  display: flex;
  align-items: center;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.65);
  padding: 1px 0;
}

.file-name {
  font-family: ui-monospace, monospace;
}

/* ── Activity Timeline (matches dev panel) ──────────────────────── */

.activity-accordion {
  opacity: 0.85;
}

.activity-log {
  max-height: 400px;
  overflow-y: auto;
}

.activity-log-item {
  display: flex;
  align-items: flex-start;
  padding: 6px 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.04);
}

.activity-log-item:last-child {
  border-bottom: none;
}
</style>
