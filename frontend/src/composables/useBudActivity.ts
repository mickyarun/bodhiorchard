// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Composable for fetching and subscribing to BUD development activity.
 *
 * Loads commits, MCP status updates, and stats via REST,
 * then subscribes to real-time WebSocket updates for live activity feed.
 *
 * Accepts an optional role filter so the same composable powers both the
 * BUD development tab (excludeRole='qa' when QA automation is enabled,
 * unfiltered otherwise) and the BUD testing tab (role='qa'). The two
 * filter modes are mutually exclusive — pass one or the other, not both.
 */
import { ref, onUnmounted } from 'vue'
import api from '@/services/api'
import { subscribe, unsubscribe } from '@/services/socket'
import type {
  DevActivity,
  DevActivityResponse,
  DevCommit,
  DevCommitRepo,
  DevContributor,
  DevStats,
  UntrackedRepo,
} from '@/types'

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

export interface BudActivityRoleFilter {
  /** When set, only commits where actor_role matches are returned. */
  role?: string
  /** When set, only commits where actor_role is NULL or != excludeRole are returned. */
  excludeRole?: string
}

export function useBudActivity(budId: string, roleFilter?: BudActivityRoleFilter) {
  const activities = ref<DevActivity[]>([])
  const commits = ref<DevCommit[]>([])
  const contributors = ref<DevContributor[]>([])
  const repos = ref<DevCommitRepo[]>([])
  const untrackedRepos = ref<UntrackedRepo[]>([])
  const stats = ref<DevStats>({ ...DEFAULT_STATS })
  const loading = ref(false)

  // The realtime topic is bud-scoped, NOT role-scoped — the backend WS
  // publish in handle_dev_activity doesn't include role info today. New
  // events come in via the topic and we filter them client-side using
  // the role field if it ever lands on the WS payload. For now we just
  // prepend everything; the next API refresh corrects any drift.
  const topic = `bud:${budId}:activity`

  function onMessage(data: unknown): void {
    activities.value.unshift(data as DevActivity)
  }

  async function load(): Promise<void> {
    loading.value = true
    try {
      // Build the role-filter query string. The backend rejects passing
      // both role + exclude_role with HTTP 400, so we honour the same
      // mutual exclusion here: role wins if the caller accidentally sets
      // both.
      const params: Record<string, string> = {}
      if (roleFilter?.role) {
        params.role = roleFilter.role
      } else if (roleFilter?.excludeRole) {
        params.exclude_role = roleFilter.excludeRole
      }
      const { data } = await api.get<DevActivityResponse>(
        `/v1/buds/${budId}/dev-activity`,
        { params },
      )
      activities.value = data.activities
      commits.value = data.commits
      contributors.value = data.contributors
      repos.value = data.repos
      untrackedRepos.value = data.untracked_repos ?? []
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

  return {
    activities,
    commits,
    contributors,
    repos,
    untrackedRepos,
    stats,
    loading,
    load,
    startListening,
    stopListening,
  }
}
