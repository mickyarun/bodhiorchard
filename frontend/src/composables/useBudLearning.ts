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

// Composable wrapping `GET /v1/buds/{id}/learning`. Used by the BUD
// detail Learnings tab. No realtime socket here — the parent
// subscribes to `bud:{id}:activity` for the `learning_recorded` event
// and calls `refresh()` when it fires; that keeps the cache shape
// shared with all the other tabs that follow the same pattern.

import { ref } from 'vue'
import api from '@/services/api'

export interface BudLearningPhaseMetric {
  actual_days: number
  estimated_days: number | null
  drift_pct: number | null
  entered_at?: string
  exited_at?: string
}

export interface BudLearningContributor {
  user_id: string
  name: string
  commits: number
  prs_merged: number
  todos_completed: number
  active_days: number
}

export interface BudLearningMetrics {
  schema_version: number
  original_estimated_days: number | null
  phase_metrics: Record<string, BudLearningPhaseMetric>
  contributors: BudLearningContributor[]
  parallelism_score: number | null
}

export interface BudLearning {
  bud_id: string
  retrospective_md: string | null
  cycle_time_days: number | null
  estimated_days: number | null
  bug_count: number
  metrics: BudLearningMetrics | null
  created_at: string
  updated_at: string
}

export function useBudLearning() {
  const learning = ref<BudLearning | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchLearning(budId: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<BudLearning>(`/v1/buds/${budId}/learning`)
      learning.value = data
    } catch (err: unknown) {
      // 404 is the normal cold-state — surface as `null`, not an error,
      // so the panel can render its empty-state callout rather than a
      // red banner. Other errors propagate to the caller.
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 404) {
        learning.value = null
      } else {
        error.value = (err as Error).message || 'Failed to load learning'
      }
    } finally {
      loading.value = false
    }
  }

  return { learning, loading, error, fetchLearning }
}
