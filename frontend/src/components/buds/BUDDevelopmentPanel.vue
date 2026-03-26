<template>
  <div class="dev-panel">
    <!-- Stats Cards -->
    <div class="stats-grid mb-4">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total_commits }}</div>
        <div class="stat-label">Commits</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.total_files_changed }}</div>
        <div class="stat-label">Files</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ formatCost(stats.total_cost_usd) }}</div>
        <div class="stat-label">AI Cost</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" :class="scoreColor">
          {{ stats.effectiveness_score || '—' }}
        </div>
        <div class="stat-label">AI Score</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.repos_touched }}</div>
        <div class="stat-label">Repos</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.agent_runs }}</div>
        <div class="stat-label">Agent Runs</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.test_coverage }}</div>
        <div class="stat-label">Tests</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.risk_count }}</div>
        <div class="stat-label">Risks</div>
      </div>
    </div>

    <!-- Activity Feed -->
    <div class="mb-4">
      <div class="text-subtitle-2 font-weight-medium mb-2">Activity</div>
      <div v-if="loading" class="d-flex justify-center py-4">
        <v-progress-circular indeterminate size="20" width="2" />
      </div>
      <div v-else-if="feed.length === 0" class="text-caption text-medium-emphasis py-4 text-center">
        No development activity yet
      </div>
      <div v-else class="activity-feed">
        <div
          v-for="item in feed"
          :key="item.id"
          class="activity-item d-flex align-start ga-2"
        >
          <v-icon
            :icon="item.icon"
            :color="item.color"
            size="16"
            class="mt-1"
          />
          <div class="flex-grow-1" style="min-width: 0;">
            <div class="text-body-2 text-truncate">{{ item.message }}</div>
            <div class="text-caption text-medium-emphasis">{{ item.time }}</div>
          </div>
          <v-chip
            v-if="item.status"
            :color="statusColor(item.status)"
            size="x-small"
            variant="tonal"
            label
          >
            {{ item.status }}
          </v-chip>
        </div>
      </div>
    </div>

    <!-- Repos & Branches -->
    <div v-if="repos.length > 0">
      <div class="text-subtitle-2 font-weight-medium mb-2">Repos & Branches</div>
      <v-card
        v-for="repo in repos"
        :key="repo.repo_path"
        variant="outlined"
        class="mb-2 pa-3"
      >
        <div class="d-flex align-center justify-space-between">
          <div>
            <div class="text-body-2 font-weight-medium">{{ repo.repo_name }}</div>
            <div class="text-caption text-medium-emphasis">
              {{ repo.commit_count }} commit{{ repo.commit_count !== 1 ? 's' : '' }}
            </div>
          </div>
          <v-chip size="x-small" variant="tonal" label>
            {{ repo.last_sha.slice(0, 7) }}
          </v-chip>
        </div>
      </v-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useBudActivity } from '@/composables/useBudActivity'
import type { DevActivity } from '@/types'

const props = defineProps<{
  budId: string
}>()

const { activities, commits, repos, stats, loading, load, startListening } = useBudActivity(props.budId)

// Merge activities + commits into a unified feed sorted by time
interface FeedItem {
  id: string
  icon: string
  color: string
  message: string
  status: string | null
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
      status: a.status,
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
      status: null,
      time: timeAgo(c.created_at),
      timestamp: new Date(c.created_at).getTime(),
    })
  }

  return items.sort((a, b) => b.timestamp - a.timestamp).slice(0, 30)
})

const scoreColor = computed(() => {
  const s = stats.value.effectiveness_score
  if (s >= 80) return 'text-success'
  if (s >= 50) return 'text-warning'
  if (s > 0) return 'text-error'
  return ''
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

onMounted(() => {
  load()
  startListening()
})

// Reload when budId changes
watch(() => props.budId, () => {
  load()
})

defineExpose({ load })
</script>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}

.stat-card {
  padding: 12px;
  border-radius: 8px;
  background: rgba(var(--v-theme-surface-variant), 0.3);
  text-align: center;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 600;
  line-height: 1.2;
}

.stat-label {
  font-size: 0.7rem;
  color: rgba(var(--v-theme-on-surface), 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-top: 2px;
}

.activity-feed {
  max-height: 400px;
  overflow-y: auto;
}

.activity-item {
  padding: 8px 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.activity-item:last-child {
  border-bottom: none;
}
</style>
