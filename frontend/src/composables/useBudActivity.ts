/**
 * Composable for fetching and subscribing to BUD development activity.
 *
 * Loads commits, MCP status updates, and stats via REST,
 * then subscribes to real-time WebSocket updates for live activity feed.
 */
import { ref, onUnmounted } from 'vue'
import api from '@/services/api'
import { subscribe, unsubscribe } from '@/services/socket'
import type { DevActivity, DevActivityResponse, DevCommit, DevCommitRepo, DevStats } from '@/types'

const DEFAULT_STATS: DevStats = {
  total_commits: 0,
  total_files_changed: 0,
  repos_touched: 0,
  agent_runs: 0,
  effectiveness_score: 0,
  confidence: 0,
  completion_rate: 0,
  cost_per_commit: 0,
  total_cost_usd: 0,
  test_coverage: 'none',
  risk_count: 0,
}

export function useBudActivity(budId: string) {
  const activities = ref<DevActivity[]>([])
  const commits = ref<DevCommit[]>([])
  const repos = ref<DevCommitRepo[]>([])
  const stats = ref<DevStats>({ ...DEFAULT_STATS })
  const loading = ref(false)

  const topic = `bud:${budId}:activity`

  function onMessage(data: unknown): void {
    activities.value.unshift(data as DevActivity)
  }

  async function load(): Promise<void> {
    loading.value = true
    try {
      const { data } = await api.get<DevActivityResponse>(`/v1/buds/${budId}/dev-activity`)
      activities.value = data.activities
      commits.value = data.commits
      repos.value = data.repos
      stats.value = data.stats
    } finally {
      loading.value = false
    }
  }

  function startListening(): void {
    subscribe(topic, onMessage)
  }

  function stopListening(): void {
    unsubscribe(topic, onMessage)
  }

  onUnmounted(stopListening)

  return { activities, commits, repos, stats, loading, load, startListening, stopListening }
}
