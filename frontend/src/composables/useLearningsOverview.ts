// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Wrapper around `GET /v1/learnings/overview`. Uses a per-session
// in-memory SWR cache (default 5 min) so navigating away and back
// doesn't re-hit the backend for an essentially-static aggregation.
// Mutations to closed BUDs are infrequent enough that staleness is
// rarely visible to the user; pass `force=true` to bypass.

import { ref } from 'vue'
import api from '@/services/api'

export interface PhaseRollup {
  phase: string
  n_samples: number
  p50_days: number | null
  p70_days: number | null
  p85_days: number | null
  running_mean: number | null
  trend_30d_pct: number | null
}

export interface ComplexityBucket {
  complexity: number
  n_samples_total: number
  phases: PhaseRollup[]
}

export interface RepeatOffender {
  phase: string
  median_drift_pct: number
  buds_over_estimate: number
  buds_total: number
}

export interface VelocityTrendPoint {
  week_start: string
  avg_cycle_days: number
  n_buds: number
}

export interface TopContributor {
  user_id: string
  name: string
  buds_shipped_30d: number
  total_commits_30d: number
  total_prs_merged_30d: number
}

export interface LearningsOverview {
  complexity_buckets: ComplexityBucket[]
  repeat_offender_phases: RepeatOffender[]
  velocity_trend: VelocityTrendPoint[]
  top_contributors: TopContributor[]
}

const FIVE_MIN_MS = 5 * 60 * 1000

let cached: LearningsOverview | null = null
let cachedAt = 0

export function useLearningsOverview() {
  const overview = ref<LearningsOverview | null>(cached)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchOverview(force = false): Promise<void> {
    if (!force && cached && Date.now() - cachedAt < FIVE_MIN_MS) {
      overview.value = cached
      return
    }
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<LearningsOverview>('/v1/learnings/overview')
      cached = data
      cachedAt = Date.now()
      overview.value = data
    } catch (err) {
      error.value = (err as Error).message || 'Failed to load learnings overview'
    } finally {
      loading.value = false
    }
  }

  function isEmpty(view: LearningsOverview | null): boolean {
    if (!view) return true
    return (
      view.complexity_buckets.length === 0
      && view.repeat_offender_phases.length === 0
      && view.velocity_trend.length === 0
      && view.top_contributors.length === 0
    )
  }

  return { overview, loading, error, fetchOverview, isEmpty }
}
