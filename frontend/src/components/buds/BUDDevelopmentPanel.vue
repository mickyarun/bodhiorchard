<template>
  <div class="dev-panel pa-4">
    <!-- Loading -->
    <div v-if="loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate size="24" width="2" />
    </div>

    <!-- Empty state: no activity yet -->
    <div v-else-if="!hasActivity" class="empty-state">
      <v-icon icon="mdi-code-braces" size="48" color="primary" class="mb-3 opacity-40" />
      <div class="text-h6 font-weight-medium mb-2">Ready for development</div>
      <div class="text-body-2 text-medium-emphasis mb-4" style="max-width: 420px;">
        Start coding on a <code>bud-{{ budNumber }}/</code> branch. Commits will appear here
        automatically via git hooks. Use Claude Code with Bodhigrove MCP to report progress.
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
      <div v-if="branchCopied" class="text-caption text-success mt-2">
        Copied: bud-{{ budNumber }}/...
      </div>
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

      <!-- Activity Feed -->
      <div class="mb-5">
        <div class="d-flex align-center mb-3">
          <div class="text-subtitle-2 font-weight-medium">Activity Feed</div>
          <v-spacer />
          <div class="text-caption text-medium-emphasis">{{ feed.length }} entries</div>
        </div>
        <div class="activity-feed">
          <div
            v-for="item in feed"
            :key="item.id"
            class="activity-item"
          >
            <div class="activity-dot" :style="{ background: `rgb(var(--v-theme-${item.color}))` }" />
            <div class="activity-content">
              <div class="text-body-2">{{ item.message }}</div>
              <div class="text-caption text-medium-emphasis">{{ item.time }}</div>
            </div>
            <v-chip
              v-if="item.chipLabel"
              :color="item.color"
              size="x-small"
              variant="tonal"
              label
              class="ml-2"
            >
              {{ item.chipLabel }}
            </v-chip>
          </div>
        </div>
      </div>

      <!-- Repos -->
      <div v-if="repos.length > 0">
        <div class="text-subtitle-2 font-weight-medium mb-3">Repositories</div>
        <div class="repos-list">
          <div
            v-for="repo in repos"
            :key="repo.repo_path"
            class="repo-card"
          >
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
import type { DevActivity } from '@/types'

const props = defineProps<{
  budId: string
  budNumber?: number
  hasTechSpec?: boolean
}>()

defineEmits<{
  (e: 'download-tech-spec'): void
}>()

const { activities, commits, repos, stats, loading, load, startListening } = useBudActivity(props.budId)
const branchCopied = ref(false)

const hasActivity = computed(() =>
  activities.value.length > 0 || commits.value.length > 0,
)

const hasEffectivenessData = computed(() =>
  activities.value.some(a => a.metadata?.effectiveness) || stats.value.total_commits > 0,
)

// Feed items
interface FeedItem {
  id: string
  icon: string
  color: string
  message: string
  chipLabel: string | null
  time: string
  timestamp: number
}

const feed = computed<FeedItem[]>(() => {
  const items: FeedItem[] = []

  for (const a of activities.value) {
    items.push({
      id: `a-${a.id}`,
      icon: activityIcon(a),
      color: statusColor(a.status),
      message: a.message,
      chipLabel: a.status,
      time: timeAgo(a.created_at),
      timestamp: new Date(a.created_at).getTime(),
    })
  }

  for (const c of commits.value) {
    items.push({
      id: `c-${c.commit_sha}`,
      icon: 'mdi-source-commit',
      color: 'grey',
      message: `${c.commit_sha.slice(0, 7)} — ${c.commit_message}`,
      chipLabel: null,
      time: timeAgo(c.created_at),
      timestamp: new Date(c.created_at).getTime(),
    })
  }

  return items.sort((a, b) => b.timestamp - a.timestamp).slice(0, 30)
})

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

function activityIcon(a: DevActivity): string {
  if (a.status === 'completed') return 'mdi-check-circle'
  if (a.status === 'failed') return 'mdi-alert-circle'
  if (a.status === 'blocked') return 'mdi-pause-circle'
  return 'mdi-progress-wrench'
}

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
  max-height: 360px;
  overflow-y: auto;
}

.activity-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 0;
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
