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
        automatically — git hooks and Bodhigrove MCP are auto-configured during repo scanning.
      </div>

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
      <!-- Stats Row -->
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
          <v-icon icon="mdi-currency-usd" size="18" color="warning" class="mb-1" />
          <div class="stat-value">{{ formatCost(stats.total_cost_usd) }}</div>
          <div class="stat-label">AI Cost</div>
        </div>
        <div class="stat-card">
          <v-icon icon="mdi-chart-arc" size="18" :color="scoreIconColor" class="mb-1" />
          <div class="stat-value" :class="scoreTextColor">
            {{ hasEffectivenessData ? stats.effectiveness_score : '—' }}
          </div>
          <div class="stat-label">AI Score</div>
        </div>
      </div>

      <!-- MCP Activity (separate from commits) -->
      <div v-if="activities.length > 0" class="mb-5">
        <div class="text-subtitle-2 font-weight-medium mb-3">Agent Updates</div>
        <div class="activity-feed">
          <div v-for="a in activities" :key="a.id" class="activity-item">
            <div class="activity-dot" :style="{ background: `rgb(var(--v-theme-${statusColor(a.status)}))` }" />
            <div class="activity-content">
              <div class="text-body-2">{{ a.message }}</div>
              <div class="text-caption text-medium-emphasis">{{ timeAgo(a.created_at) }}</div>
            </div>
            <v-chip :color="statusColor(a.status)" size="x-small" variant="tonal" label class="ml-2">
              {{ a.status }}
            </v-chip>
          </div>
        </div>
      </div>

      <!-- Contributors (grouped by developer) -->
      <div v-if="contributors.length > 0" class="mb-5">
        <div class="d-flex align-center mb-3">
          <div class="text-subtitle-2 font-weight-medium">Contributors</div>
          <v-spacer />
          <div class="text-caption text-medium-emphasis">{{ contributors.length }} developer{{ contributors.length !== 1 ? 's' : '' }}</div>
        </div>
        <v-expansion-panels variant="accordion">
          <v-expansion-panel
            v-for="dev in contributors"
            :key="dev.user_id || dev.author_email || 'unknown'"
          >
            <v-expansion-panel-title>
              <div class="d-flex align-center ga-2 flex-grow-1">
                <v-avatar size="28" color="surface-variant">
                  <span class="text-caption font-weight-bold">
                    {{ (dev.user_name || dev.author_name || '?')[0].toUpperCase() }}
                  </span>
                </v-avatar>
                <div>
                  <span class="text-body-2 font-weight-medium">
                    {{ dev.user_name || dev.author_name || dev.author_email || 'Unknown' }}
                  </span>
                  <span v-if="!dev.user_id && dev.author_email" class="text-caption text-medium-emphasis ml-1">
                    ({{ dev.author_email }})
                  </span>
                </div>
                <v-spacer />
                <v-chip size="x-small" variant="tonal" class="mr-2">
                  {{ dev.commit_count }} commit{{ dev.commit_count !== 1 ? 's' : '' }}
                </v-chip>
                <v-chip size="x-small" variant="tonal" color="teal">
                  {{ dev.files_changed }} file{{ dev.files_changed !== 1 ? 's' : '' }}
                </v-chip>
              </div>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <div
                v-for="c in dev.commits"
                :key="c.commit_sha"
                class="commit-row"
              >
                <code class="text-caption">{{ c.commit_sha.slice(0, 7) }}</code>
                <span class="text-body-2 mx-2">{{ c.commit_message }}</span>
                <v-spacer />
                <span class="text-caption text-medium-emphasis">{{ timeAgo(c.created_at) }}</span>
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </div>

      <!-- Repos -->
      <div v-if="repos.length > 0">
        <div class="text-subtitle-2 font-weight-medium mb-3">Repositories</div>
        <div class="repos-list">
          <div v-for="repo in repos" :key="repo.repo_path" class="repo-card">
            <v-icon icon="mdi-source-repository" size="18" color="primary" class="mr-2" />
            <div class="flex-grow-1">
              <div class="text-body-2 font-weight-medium">{{ repo.repo_name }}</div>
              <div class="text-caption text-medium-emphasis">
                {{ repo.commit_count }} commit{{ repo.commit_count !== 1 ? 's' : '' }}
                &middot; latest {{ repo.last_sha.slice(0, 7) }}
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useBudActivity } from '@/composables/useBudActivity'

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

const hasEffectivenessData = computed(() =>
  activities.value.some(a => a.metadata?.effectiveness) || stats.value.total_commits > 0,
)

const scoreIconColor = computed(() => {
  if (!hasEffectivenessData.value) return 'grey'
  const s = stats.value.effectiveness_score
  if (s >= 80) return 'success'
  if (s >= 50) return 'warning'
  return 'error'
})

const scoreTextColor = computed(() => {
  if (!hasEffectivenessData.value) return 'text-medium-emphasis'
  const s = stats.value.effectiveness_score
  if (s >= 80) return 'text-success'
  if (s >= 50) return 'text-warning'
  return 'text-error'
})

function statusColor(status: string): string {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'error'
  if (status === 'blocked') return 'warning'
  return 'info'
}

function formatCost(cost: number): string {
  if (!cost) return '$0'
  if (cost < 0.01) return `$${cost.toFixed(3)}`
  return `$${cost.toFixed(2)}`
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

.activity-feed {
  max-height: 300px;
  overflow-y: auto;
}

.activity-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.activity-item:last-child {
  border-bottom: none;
}

.activity-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
}

.activity-content {
  flex: 1;
  min-width: 0;
}

.commit-row {
  display: flex;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.04);
}

.commit-row:last-child {
  border-bottom: none;
}

.repos-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.repo-card {
  display: flex;
  align-items: center;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
</style>
