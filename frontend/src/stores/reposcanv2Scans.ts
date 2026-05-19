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
 * Pinia store for the multi-repo scan page (timeline, resume).
 *
 * Wraps `/api/v1/reposcanv2/{config,repos,scans/...}`. Backed by the
 * production `app/reposcanv2/scans_api.py` router on the backend.
 *
 * Polling: while a scan is queued/running we hit `GET /scans/{id}`
 * every 2s. Stops automatically when the scan reaches a terminal
 * status.
 *
 * Persistence: none on the client. On every page mount we ask the
 * backend for the most-recent scan (`GET /scans/latest`) so the
 * timeline + per-repo chips rehydrate from the database — the same
 * source of truth across browsers, sessions, and tabs.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import api from '@/services/api'

/** Mirrors `app.models.reposcanv2_enums.RepoRunStatus`. */
export type RepoRunStatus
  = | 'queued' | 'running' | 'done' | 'failed' | 'skipped_unchanged' | 'cancelled'

/** Mirrors `app.models.reposcanv2_enums.StepStatus`. */
export type StepStatus
  = | 'queued' | 'running' | 'done' | 'failed' | 'skipped_cache' | 'skipped'

/** Mirrors `app.models.scan_phase.ScanPhase`. */
export type ScanPhase
  = | 'mode_detection' | 'code_index' | 'repo_setup' | 'stale_cleanup'
    | 'skill_extraction' | 'design_system_extract' | 'feature_synthesis'
    | 'extract_routes' | 'skill_remap' | 'feature_merge' | 'backend_link'
    | 'embedding_backfill' | 'persist_results'

/** Mirrors `app.models.tracked_repository.RepoStatus`. */
export type RepoStatus = 'active' | 'inactive' | 'archived'

export interface RepoCard {
  id: string
  name: string
  path: string
  status: RepoStatus
  head_sha: string | null
  last_scanned_at: string | null
  feature_count: number
  /** Status of the most recent ScanRepoRun for this repo, across all
   *  scans. `null` when the repo has never been scanned. The Settings
   *  → Code list renders this as a pill on rows not in the in-flight
   *  scan so the user sees recency + outcome at a glance. */
  last_scan_status: RepoRunStatus | null
  last_scan_finished_at: string | null
  last_scan_started_at: string | null
  last_scan_feature_count: number | null
  last_scan_id: string | null
}

export interface StepRow {
  phase: ScanPhase
  status: StepStatus
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  input_count: number
  kept_count: number
  dropped_count: number
  error: string | null
  /** Per-stage payload (counts, derived labels, MCP status, etc.). */
  extras: Record<string, unknown>
}

export interface RepoRunRow {
  repo_id: string
  repo_name: string
  status: RepoRunStatus
  head_sha_at_start: string | null
  started_at: string | null
  finished_at: string | null
  feature_count: number | null
  error: string | null
  steps: StepRow[]
}

export interface ScanDetail {
  scan_id: string
  status: string
  started_at: string
  repo_runs: RepoRunRow[]
}

export interface V2Config {
  default_model: string
  default_max_turns: number
  default_timeout_seconds: number
  known_phases: ScanPhase[]
}

interface StartScanResponse {
  // Null when every requested repo took the diff-based rescan
  // fast path — there's no Scan row to poll because the work is
  // happening on the per-(org, repo) PR-merge Redis stream.
  scan_id: string | null
  status: string
  repo_count: number
  rescan_delivery_ids?: string[]
  rescan_repo_count?: number
}

interface ResumeResponse {
  scan_id: string
  requeued: number
}

const POLL_INTERVAL_MS = 2000
const TERMINAL_REPO_RUN: ReadonlySet<RepoRunStatus> = new Set([
  'done', 'failed', 'skipped_unchanged', 'cancelled',
])
// Aggregate ``scans.status`` values that mean "no further server-side
// work for this scan". Anything outside this set — even when every
// per-repo run is already terminal — keeps the UI locked because the
// global phases (feature_merge / skill_remap / embedding_backfill /
// persist_results) still need to run before another scan can start.
const TERMINAL_SCAN_STATUS: ReadonlySet<string> = new Set([
  'completed', 'failed', 'cancelled',
])

export const useReposcanV2ScansStore = defineStore('reposcanv2Scans', () => {
  // --- state -------------------------------------------------------
  const config = ref<V2Config | null>(null)
  const repos = ref<RepoCard[]>([])
  const selectedRepoIds = ref<Set<string>>(new Set())
  const currentScan = ref<ScanDetail | null>(null)

  const loadingRepos = ref(false)
  const loadingScan = ref(false)
  const startingScan = ref(false)
  const cancellingScan = ref(false)
  const error = ref<string | null>(null)

  let pollHandle: number | null = null

  // --- derived -----------------------------------------------------
  const isCurrentScanActive = computed(() => {
    const scan = currentScan.value
    if (!scan) return false
    // Lock the UI until BOTH conditions clear:
    //   1. every per-repo run reached a terminal state, AND
    //   2. the aggregate scan row reached one too.
    // Condition 2 is what extends the lock through the four global
    // finalization phases (feature_merge → persist_results), which run
    // after per-repo work but before ``_mark_scan_terminal``. Without
    // the aggregate check the Scan button re-enables the moment the
    // last repo's per-repo stages finish, even though feature_merge
    // is still synthesising — and a second scan started then would
    // collide with the in-flight global phases.
    const someRepoActive = scan.repo_runs.some(
      run => !TERMINAL_REPO_RUN.has(run.status),
    )
    const aggregateActive = !TERMINAL_SCAN_STATUS.has(scan.status)
    return someRepoActive || aggregateActive
  })

  const aggregateCounts = computed(() => {
    const runs = currentScan.value?.repo_runs ?? []
    const total = runs.length
    const done = runs.filter(r => r.status === 'done' || r.status === 'skipped_unchanged').length
    const running = runs.filter(r => r.status === 'running').length
    const failed = runs.filter(r => r.status === 'failed').length
    const queued = runs.filter(r => r.status === 'queued').length
    const features = runs.reduce((sum, r) => sum + (r.feature_count ?? 0), 0)
    return { total, done, running, failed, queued, features }
  })

  // --- actions -----------------------------------------------------
  async function loadConfig(): Promise<void> {
    if (config.value !== null) return
    try {
      const { data } = await api.get<V2Config>('/v1/reposcanv2/config')
      config.value = data
    } catch (err) {
      error.value = extractMessage(err, 'Failed to load v2 config')
    }
  }

  async function fetchRepos(): Promise<void> {
    loadingRepos.value = true
    try {
      const { data } = await api.get<RepoCard[]>('/v1/reposcanv2/repos')
      repos.value = data
      // Drop selections that no longer exist (e.g. a repo was removed).
      const known = new Set(data.map(r => r.id))
      selectedRepoIds.value = new Set(
        Array.from(selectedRepoIds.value).filter(id => known.has(id)),
      )
      error.value = null
    } catch (err) {
      error.value = extractMessage(err, 'Failed to load repositories')
    } finally {
      loadingRepos.value = false
    }
  }

  function toggleRepo(id: string): void {
    const next = new Set(selectedRepoIds.value)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    selectedRepoIds.value = next
  }

  function selectAllActive(): void {
    selectedRepoIds.value = new Set(
      repos.value.filter(r => r.status === 'active').map(r => r.id),
    )
  }

  function selectStale(): void {
    selectedRepoIds.value = new Set(
      repos.value
        .filter(r => r.status === 'active' && (r.head_sha === null || r.last_scanned_at === null))
        .map(r => r.id),
    )
  }

  function clearSelection(): void {
    selectedRepoIds.value = new Set()
  }

  async function startScan(): Promise<string | null> {
    if (selectedRepoIds.value.size === 0) {
      error.value = 'Select at least one repository to scan'
      return null
    }
    // Wipe the prior scan immediately so the timeline doesn't keep
    // rendering green DONE chips from the last run while we wait for
    // the new scan id + first /scans/{id} response. Polling is also
    // stopped so it doesn't race with the about-to-arrive new state.
    stopPolling()
    currentScan.value = null
    startingScan.value = true
    try {
      // Always send full_rescan=false explicitly. RunConfig defaults to
      // True server-side, which would force a soft-delete + full rebuild
      // every scan and defeat the SHA-unchanged short-circuit.
      const body: { repo_ids: string[]; config: { full_rescan: boolean } } = {
        repo_ids: Array.from(selectedRepoIds.value),
        config: { full_rescan: false },
      }
      const { data } = await api.post<StartScanResponse>('/v1/reposcanv2/scans', body)
      error.value = null
      // ``scan_id`` is null when every requested repo took the rescan
      // fast path — there's no Scan row to poll. The diff-based work
      // runs on the PR-merge Redis stream and progress shows up in
      // the deliveries log, not the timeline.
      if (data.scan_id) {
        await fetchScan(data.scan_id)
      }
      return data.scan_id
    } catch (err) {
      // 409 = a scan is already running for this org. Switch the timeline
      // to it instead of surfacing an error — the user almost certainly
      // wants to watch the in-flight one rather than queue a new request.
      const conflict = extractConflictScanId(err)
      if (conflict !== null) {
        error.value = 'A scan is already running — switched to it.'
        await fetchScan(conflict)
        return conflict
      }
      error.value = extractMessage(err, 'Failed to start scan')
      return null
    } finally {
      startingScan.value = false
    }
  }

  async function fetchScan(scanId: string): Promise<void> {
    loadingScan.value = true
    try {
      const { data } = await api.get<ScanDetail>(`/v1/reposcanv2/scans/${scanId}`)
      currentScan.value = data
      error.value = null
      ensurePolling()
    } catch (err) {
      error.value = extractMessage(err, 'Failed to load scan')
      currentScan.value = null
    } finally {
      loadingScan.value = false
    }
  }

  /** On page mount: load the most-recent scan for this org so the
   * timeline + per-repo chips rehydrate from the database. 404 means
   * the org has never scanned — that's fine, the page stays idle. */
  async function restoreActiveScan(): Promise<void> {
    loadingScan.value = true
    try {
      const { data } = await api.get<ScanDetail>('/v1/reposcanv2/scans/latest')
      currentScan.value = data
      error.value = null
      ensurePolling()
    } catch (err) {
      if (err && typeof err === 'object' && 'response' in err) {
        const status = (err as { response?: { status?: number } }).response?.status
        if (status === 404) return
      }
      error.value = extractMessage(err, 'Failed to load last scan')
    } finally {
      loadingScan.value = false
    }
  }

  /** Cancel the in-flight scan: hits POST /api/v1/scan/{id}/cancel,
   * which flips the aggregate scan row to ``failed`` and cascades the
   * terminal status into every non-terminal scan_repo_runs /
   * scan_repo_steps row so the per-repo timeline clears at the same
   * moment as the banner. After the call returns, refresh the scan
   * detail and repo card list so the UI reflects the new state. */
  async function cancelActiveScan(): Promise<boolean> {
    const scan = currentScan.value
    if (scan === null) {
      return false
    }
    cancellingScan.value = true
    try {
      await api.post(`/v1/reposcanv2/scans/${scan.scan_id}/cancel`)
      stopPolling()
      await Promise.all([fetchScan(scan.scan_id), fetchRepos()])
      error.value = null
      return true
    } catch (err) {
      error.value = extractMessage(err, 'Failed to cancel scan')
      return false
    } finally {
      cancellingScan.value = false
    }
  }

  async function resumeScan(scanId: string): Promise<number> {
    try {
      const { data } = await api.post<ResumeResponse>(
        `/v1/reposcanv2/scans/${scanId}/resume`,
      )
      await fetchScan(scanId)
      return data.requeued
    } catch (err) {
      error.value = extractMessage(err, 'Failed to resume scan')
      return 0
    }
  }

  function ensurePolling(): void {
    if (!isCurrentScanActive.value) {
      stopPolling()
      return
    }
    if (pollHandle !== null) return
    pollHandle = window.setInterval(async () => {
      const id = currentScan.value?.scan_id
      if (!id) {
        stopPolling()
        return
      }
      try {
        const { data } = await api.get<ScanDetail>(`/v1/reposcanv2/scans/${id}`)
        currentScan.value = data
        if (!isCurrentScanActive.value) {
          stopPolling()
          // The just-finished scan changed each repo's last-scan
          // summary on the server. Refresh the card list so rows that
          // were rendering the live timeline flip back to the new
          // "done • N features • <relative time>" summary without
          // requiring the user to reload.
          void fetchRepos()
        }
      } catch {
        // Transient errors are non-fatal during polling.
      }
    }, POLL_INTERVAL_MS)
  }

  function stopPolling(): void {
    if (pollHandle !== null) {
      window.clearInterval(pollHandle)
      pollHandle = null
    }
  }

  /** Stop polling without clearing `currentScan` — called on route
   * unmount. The next mount calls `restoreActiveScan()` which re-reads
   * the latest scan from the API. */
  function pausePolling(): void {
    stopPolling()
  }

  return {
    // state
    config,
    repos,
    selectedRepoIds,
    currentScan,
    loadingRepos,
    loadingScan,
    startingScan,
    cancellingScan,
    error,
    // derived
    isCurrentScanActive,
    aggregateCounts,
    // actions
    loadConfig,
    fetchRepos,
    toggleRepo,
    selectAllActive,
    selectStale,
    clearSelection,
    startScan,
    fetchScan,
    restoreActiveScan,
    resumeScan,
    cancelActiveScan,
    pausePolling,
  }
})

function extractMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const response = (err as { response?: { data?: { detail?: unknown } } }).response
    const detail = response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail.length > 0) return JSON.stringify(detail)
  }
  if (err instanceof Error) return err.message
  return fallback
}

/** Pulls the in-flight scan_id out of the backend's 409 payload. The
 *  shape comes from `scans_api.create_scan` — `{error, scan_id, status,
 *  message}` packed into FastAPI's `detail`. Returns null when the
 *  error isn't a recognised scan conflict. */
function extractConflictScanId(err: unknown): string | null {
  if (!err || typeof err !== 'object' || !('response' in err)) return null
  const response = (err as { response?: { status?: number; data?: { detail?: unknown } } }).response
  if (response?.status !== 409) return null
  const detail = response.data?.detail
  if (detail && typeof detail === 'object' && 'scan_id' in detail) {
    const scanId = (detail as { scan_id?: unknown }).scan_id
    if (typeof scanId === 'string' && scanId.length > 0) return scanId
  }
  return null
}
