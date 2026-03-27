<template>
  <div class="dev-panel pa-4">
    <!-- Loading -->
    <div v-if="loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate size="24" width="2" />
    </div>

    <!-- Empty state -->
    <div v-else-if="!hasActivity" class="empty-state">
      <v-icon icon="mdi-code-braces" size="48" color="primary" class="mb-3 opacity-40" />
      <div class="text-h6 font-weight-medium mb-2">Ready for development</div>
      <div class="text-body-2 text-medium-emphasis mb-4" style="max-width: 440px;">
        Start coding on a <code>bud-{{ budNumber }}/</code> branch. Commits will appear here
        automatically via git hooks.
      </div>

      <!-- MCP setup guide -->
      <v-card variant="outlined" class="mb-4 pa-3 text-left" style="max-width: 440px;">
        <div class="d-flex align-center ga-2 mb-2">
          <v-icon icon="mdi-wrench" size="16" color="primary" />
          <span class="text-body-2 font-weight-medium">Setup MCP Token</span>
        </div>
        <ol class="text-caption text-medium-emphasis pl-4" style="margin: 0;">
          <li>Go to <strong>Settings → Integrations → MCP Token</strong></li>
          <li>Generate and copy your token</li>
          <li>Run: <code>export BODHIGROVE_MCP_TOKEN="your-token"</code></li>
          <li>Restart Claude Code in the repo</li>
        </ol>
      </v-card>

      <!-- Impacted repos hint -->
      <div v-if="impactedRepos && impactedRepos.length" class="mb-4">
        <div class="text-caption text-medium-emphasis mb-1">Impacted repositories</div>
        <div class="d-flex ga-2 flex-wrap justify-center">
          <v-chip
            v-for="r in impactedRepos"
            :key="r.repo_id || r.repo_name"
            size="small"
            variant="tonal"
            prepend-icon="mdi-source-repository"
          >
            {{ r.repo_name }}
          </v-chip>
        </div>
      </div>

      <div class="d-flex ga-2 justify-center">
        <v-btn
          v-if="hasTechSpec"
          variant="tonal"
          size="small"
          prepend-icon="mdi-download"
          @click="$emit('download-tech-spec')"
        >
          Download Tech Spec
        </v-btn>
        <v-btn
          variant="outlined"
          size="small"
          prepend-icon="mdi-content-copy"
          @click="copyBranchName"
        >
          Copy Branch Name
        </v-btn>
      </div>
      <div v-if="branchCopied" class="text-caption text-success mt-2">Copied!</div>
    </div>

    <!-- Has activity -->
    <template v-else>
      <!-- Stats Row: only real, useful numbers -->
      <div class="stats-row mb-5">
        <div class="stat-card">
          <v-icon icon="mdi-source-commit" size="18" color="primary" class="mb-1" />
          <div class="stat-value">{{ stats.total_commits }}</div>
          <div class="stat-label">Commits</div>
        </div>
        <div class="stat-card">
          <v-icon icon="mdi-file-multiple" size="18" color="teal" class="mb-1" />
          <div class="stat-value">{{ stats.total_files_changed }}</div>
          <div class="stat-label">Files</div>
        </div>
        <div class="stat-card">
          <v-icon icon="mdi-account-group" size="18" color="blue" class="mb-1" />
          <div class="stat-value">{{ sessionCount }}</div>
          <div class="stat-label">Sessions</div>
        </div>
        <div class="stat-card" :class="{ 'stat-card--warn': errorCount > 0 }">
          <v-icon
            :icon="errorCount > 0 ? 'mdi-alert-circle' : 'mdi-check-circle'"
            size="18"
            :color="errorCount > 0 ? 'error' : 'success'"
            class="mb-1"
          />
          <div class="stat-value" :class="errorCount > 0 ? 'text-error' : 'text-success'">
            {{ errorCount > 0 ? errorCount : '0' }}
          </div>
          <div class="stat-label">Errors</div>
        </div>
      </div>

      <!-- Health indicators row -->
      <div v-if="stats.test_coverage !== 'none' || stats.repos_touched > 0" class="health-row mb-5">
        <v-chip
          v-if="stats.test_coverage !== 'none'"
          size="small"
          variant="tonal"
          :color="stats.test_coverage === 'full' ? 'success' : 'warning'"
          prepend-icon="mdi-test-tube"
        >
          Tests: {{ stats.test_coverage }}
        </v-chip>
        <v-chip
          v-if="stats.repos_touched > 0"
          size="small"
          variant="tonal"
          prepend-icon="mdi-source-repository"
        >
          {{ stats.repos_touched }} repo{{ stats.repos_touched !== 1 ? 's' : '' }}
        </v-chip>
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

      <!-- Commits by contributor — the ONE place commit info lives -->
      <div v-if="contributors.length > 0" class="mb-5">
        <div class="section-header mb-3">
          <span class="text-subtitle-2 font-weight-medium">Commits</span>
        </div>

        <div v-for="dev in contributors" :key="dev.user_id || dev.author_email || 'unknown'" class="contributor-block">
          <!-- Contributor header -->
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

          <!-- Commits for this contributor -->
          <div class="commit-list">
            <div
              v-for="c in dev.commits"
              :key="c.commit_sha"
              class="commit-entry"
            >
              <div class="commit-header">
                <code class="commit-sha">{{ c.commit_sha.slice(0, 7) }}</code>
                <span class="commit-msg text-body-2">{{ c.commit_message }}</span>
                <span class="text-caption text-medium-emphasis text-no-wrap ml-auto">{{ timeAgo(c.created_at) }}</span>
              </div>
              <!-- Files for this commit -->
              <div v-if="parseFiles(c.files_changed).length > 0" class="commit-files">
                <div
                  v-for="file in parseFiles(c.files_changed)"
                  :key="file"
                  class="file-row"
                >
                  <v-icon :icon="fileIcon(file)" size="12" :color="fileColor(file)" class="mr-1" />
                  <span class="file-name">{{ file }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Activity Timeline — collapsible, for power users -->
      <v-expansion-panels v-if="activities.length > 0" variant="accordion" class="activity-accordion">
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useBudActivity } from '@/composables/useBudActivity'
import type { DevActivity } from '@/types'

const props = defineProps<{
  budId: string
  budNumber?: number
  hasTechSpec?: boolean
  impactedRepos?: { repo_id: string; repo_name: string }[] | null
}>()

defineEmits<{
  (e: 'download-tech-spec'): void
}>()

const { activities, contributors, repos, stats, loading, load, startListening } = useBudActivity(props.budId)
const branchCopied = ref(false)

const hasActivity = computed(() =>
  activities.value.length > 0 || contributors.value.length > 0,
)

// Count unique sessions
const sessionCount = computed(() => {
  const sessions = new Set<string>()
  for (const a of activities.value) {
    if (a.session_id) sessions.add(a.session_id)
  }
  return sessions.size || (activities.value.length > 0 ? 1 : 0)
})

// Count errors from activity events
const errorCount = computed(() =>
  activities.value.filter(a =>
    a.event_type === 'tool_error' || a.event_type === 'api_error' || a.status === 'failed',
  ).length,
)

function statusColor(status: string): string {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'blocked') return 'warning'
  return 'info'
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function parseFiles(raw: string): string[] {
  if (!raw) return []
  return raw.split(',').map(f => f.trim()).filter(Boolean)
}

function fileIcon(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  if (['vue', 'tsx', 'jsx'].includes(ext)) return 'mdi-vuejs'
  if (['ts', 'js'].includes(ext)) return 'mdi-language-typescript'
  if (['py'].includes(ext)) return 'mdi-language-python'
  if (['css', 'scss'].includes(ext)) return 'mdi-palette'
  if (['md'].includes(ext)) return 'mdi-file-document'
  if (['json', 'yaml', 'yml', 'toml'].includes(ext)) return 'mdi-code-json'
  if (['test', 'spec'].some(t => path.includes(t))) return 'mdi-test-tube'
  return 'mdi-file-outline'
}

function fileColor(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || ''
  if (['vue', 'tsx', 'jsx'].includes(ext)) return 'teal'
  if (['ts', 'js'].includes(ext)) return 'blue'
  if (['py'].includes(ext)) return 'amber'
  if (['test', 'spec'].some(t => path.includes(t))) return 'purple'
  return 'grey'
}

function eventIcon(a: DevActivity): string {
  const et = (a as any).event_type || ''
  if (et === 'commit') return 'mdi-source-commit'
  if (et === 'file_change') return 'mdi-file-edit'
  if (et === 'session_start') return 'mdi-play-circle'
  if (et === 'session_end') return 'mdi-stop-circle'
  if (et === 'tool_error' || et === 'api_error') return 'mdi-alert-circle'
  if (et === 'activity_summary') return 'mdi-text-box-check'
  if (a.status === 'completed') return 'mdi-check-circle'
  if (a.status === 'failed') return 'mdi-alert-circle'
  return 'mdi-information'
}

function eventColor(a: DevActivity): string {
  const et = (a as any).event_type || ''
  if (et === 'tool_error' || et === 'api_error') return 'error'
  if (et === 'commit') return 'primary'
  if (et === 'session_start') return 'success'
  if (et === 'session_end') return 'grey'
  return statusColor(a.status)
}

async function copyBranchName(): Promise<void> {
  const name = `bud-${String(props.budNumber || 0).padStart(3, '0')}/`
  await navigator.clipboard.writeText(name)
  branchCopied.value = true
  setTimeout(() => { branchCopied.value = false }, 2000)
}

onMounted(() => {
  load()
  startListening()
})

watch(() => props.budId, () => load())

defineExpose({ load })
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 16px;
  text-align: center;
}

/* Stats row */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 12px;
  border-radius: 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface-variant), 0.15);
}

.stat-card--warn {
  border-color: rgba(var(--v-theme-error), 0.25);
  background: rgba(var(--v-theme-error), 0.04);
}

.stat-value {
  font-size: 1.5rem;
  font-weight: 700;
  line-height: 1.2;
}

.stat-label {
  font-size: 0.65rem;
  color: rgba(var(--v-theme-on-surface), 0.45);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  margin-top: 4px;
}

/* Health indicators */
.health-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

/* Section header */
.section-header {
  display: flex;
  align-items: center;
}

/* Contributor block */
.contributor-block {
  margin-bottom: 16px;
}

.contributor-block:last-child {
  margin-bottom: 0;
}

.contributor-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

/* Commit list */
.commit-list {
  padding-left: 32px;
  border-left: 2px solid rgba(var(--v-theme-primary), 0.15);
}

.commit-entry {
  padding: 10px 0 10px 12px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.04);
}

.commit-entry:last-child {
  border-bottom: none;
}

.commit-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.commit-sha {
  font-size: 0.75rem;
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
}

.commit-msg {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* File rows — clean list, no chips */
.commit-files {
  margin-top: 6px;
  padding-left: 4px;
}

.file-row {
  display: flex;
  align-items: center;
  padding: 1px 0;
}

.file-name {
  font-family: monospace;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

/* Activity accordion */
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
