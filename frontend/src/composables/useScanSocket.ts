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

/**
 * Scan-specific composable that pushes status via WebSocket with
 * automatic polling fallback.
 *
 * Thin wrapper around useRealtimeTracker — same callback interface:
 *   const { scanData, isActive, startTracking, stopTracking } = useScanSocket()
 *   startTracking(scanId, { onProgress, onComplete, onError })
 */
import { useRealtimeTracker } from '@/composables/useRealtimeTracker'
import type { TrackerCallbacks } from '@/composables/useRealtimeTracker'

export interface RepoScanWarning {
  repo: string
  phase: string
  summary: string
  hint: string | null
}

/** Matches backend `ScanPhase` enum values. Stringly-typed here since
 * the TS side doesn't generate the enum from the Python source — one
 * new phase requires adding a string in both places, caught immediately
 * because the timeline component won't render unknown phases.
 *
 * Internal: only consumed by `PhaseStatus` below. Not exported. */
type ScanPhaseCode =
  | 'mode_detection'
  | 'code_index'
  | 'repo_setup'
  | 'stale_cleanup'
  | 'skill_extraction'
  | 'design_system_extract'
  | 'feature_synthesis'
  | 'extract_routes'
  | 'skill_remap'
  | 'backend_link'
  | 'embedding_backfill'
  | 'persist_results'

/** Internal: only consumed by `PhaseStatus` below. */
type PhaseCheckpointStatus =
  | 'pending'
  | 'running'
  | 'done'
  | 'failed'
  | 'skipped'

/** One row in the per-phase timeline the `ScanPhaseTimeline` renders. */
export interface PhaseStatus {
  phase: ScanPhaseCode
  phaseLabel: string
  scope: 'per_repo' | 'global'
  repoId: string | null
  repoName: string | null
  status: PhaseCheckpointStatus
  attempt: number
  errorCode: string | null
  errorMessage: string | null
  startedAt: string | null
  finishedAt: string | null
  /** True when the checkpoint was copied from a prior scan's DONE row
   * with matching SHA — the phase body didn't actually run this time. */
  shaReused: boolean
}

export interface ScanStatusData {
  scanId: string
  status: string
  statusLabel: string
  scanMode: string
  progressPct: number
  featuresIndexed: number
  featuresSkipped: number
  profilesFound: number
  staleCleaned: number
  unmatchedAuthors: string[]
  synthesisWarning: string | null
  setupPrMessage: string | null
  repoWarnings: RepoScanWarning[]
  /** Per-phase timeline. Empty on legacy / pre-migration scans — the
   * UI must fall back to the aggregate progress bar in that case. */
  phases: PhaseStatus[]
  /** Set on resumed / retried scans; points back to the scan this one
   * inherits done/skipped checkpoints from. */
  parentScanId: string | null
  error: string | null
}

export function useScanSocket() {
  const tracker = useRealtimeTracker<ScanStatusData>({
    topicPrefix: 'scan',
    pollEndpoint: (id) => `/v1/reposcanv2/scans/${id}/status`,
    isTerminal: (d) =>
      d.status === 'completed' ? 'completed' : d.status === 'failed' ? 'failed' : null,
    getError: (d) => d.error || null,
    pollIntervalMs: 2000,
    // No wall-clock cap: scans can legitimately run for hours (multi-repo
    // × Claude synthesis). The tracker stops when the backend reports
    // completed / failed (including the stale-sweep auto-fail), so a
    // hardcoded ceiling here only ever produces false "failed" banners.
    // Polling alongside the WS closes the subscribe → publish race:
    // the event bus has no buffer, so a terminal event published while
    // the tab was mid-unsubscribe would be lost; the next REST poll
    // catches up from Redis. Cheap insurance.
    pollAlongsideWs: true,
  })

  return {
    scanData: tracker.data,
    isActive: tracker.isActive,
    startTracking: (scanId: string, cbs?: TrackerCallbacks<ScanStatusData>) =>
      tracker.startTracking(scanId, cbs),
    stopTracking: tracker.stopTracking,
  }
}
