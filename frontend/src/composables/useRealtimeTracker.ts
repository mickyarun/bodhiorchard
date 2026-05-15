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
 * Generic real-time tracker with WebSocket push and polling fallback.
 *
 * Extracts the shared WS+polling pattern used by both useJobSocket and
 * useScanSocket. Fixes the WS-drop-mid-tracking bug by periodically
 * checking connection health and starting/stopping polling as needed.
 *
 * Usage:
 *   const tracker = useRealtimeTracker<MyData>({
 *     topicPrefix: 'scan',
 *     pollEndpoint: (id) => `/v1/reposcanv2/scans/${id}/status`,
 *     isTerminal: (d) => d.status === 'completed' ? 'completed' : d.status === 'failed' ? 'failed' : null,
 *     getError: (d) => d.error || null,
 *   })
 */
import { ref, onUnmounted } from 'vue'
import { subscribe, unsubscribe, isConnected } from '@/services/socket'
import api from '@/services/api'
import type { AxiosError } from 'axios'

export interface TrackerCallbacks<T> {
  onProgress?: (data: T) => void
  onComplete?: (data: T) => void
  onError?: (error: string, errorCode?: string | null) => void
}

export interface TrackerConfig<T> {
  /** Topic prefix — combined with id as `{prefix}:{id}` */
  topicPrefix: string
  /** Returns the polling endpoint path for a given id */
  pollEndpoint: (id: string) => string
  /** Returns 'completed' | 'failed' if terminal, null otherwise */
  isTerminal: (data: T) => 'completed' | 'failed' | null
  /** Extracts error message from data */
  getError: (data: T) => string | null
  /** Extracts a stable error category code from data (optional). */
  getErrorCode?: (data: T) => string | null
  /** Extracts result from data (optional, for job-style tracking) */
  getResult?: (data: T) => unknown
  /** Polling interval in ms (default: 2000) */
  pollIntervalMs?: number
  /**
   * Max polling duration in ms. Default is ``Infinity`` — the tracker
   * runs until the backend reports a terminal status (``completed`` /
   * ``failed``) or a persistent error. A finite value is a last-resort
   * safety valve only; for long-running resources (scans, builds) leave
   * it unset so the UI never gives up before the backend does.
   */
  pollTimeoutMs?: number
  /** Delay before falling back to polling (default: 3000) */
  fallbackDelayMs?: number
  /** Interval for WS health checks in ms (default: 5000) */
  connectionCheckMs?: number
  /**
   * When true, keep polling running alongside the WebSocket as a safety
   * net against subscribe-before-publish races (relevant for scans
   * whose progress lives in Redis for ~30 min and whose terminal event
   * can be published before the client subscribe propagates).
   *
   * When false (default), polling is only a fallback — it kicks in if
   * the WS isn't connected and stops again once it reconnects. This
   * matters for trackers whose backend state is short-lived (jobs are
   * cleaned up 5 min after terminal): a poll running after cleanup
   * would 404 and surface as a spurious "Failed to check status".
   */
  pollAlongsideWs?: boolean
  /**
   * When true (default), ``startTracking`` fires a one-shot REST fetch
   * to seed the initial state so the UI doesn't have to wait for the
   * first WS event. Useful for page-refresh-mid-scan where the user
   * lands on a tracked resource that's already in progress.
   *
   * Set false for pure WS-driven trackers whose backend state is
   * short-lived — the REST endpoint returns 404 when the entry was
   * already cleaned up, which then fires a spurious ``onError``.
   * Jobs (see ``useJobSocket``) are the canonical case.
   */
  fetchInitialStateViaRest?: boolean
}

export function useRealtimeTracker<T>(config: TrackerConfig<T>) {
  const data = ref<T | null>(null)
  const isActive = ref(false)

  const pollIntervalMs = config.pollIntervalMs ?? 2000
  const pollTimeoutMs = config.pollTimeoutMs ?? Number.POSITIVE_INFINITY
  const fallbackDelayMs = config.fallbackDelayMs ?? 3000
  const connectionCheckMs = config.connectionCheckMs ?? 5000
  const pollAlongsideWs = config.pollAlongsideWs ?? false
  const fetchInitialStateViaRest = config.fetchInitialStateViaRest ?? true

  let currentId: string | null = null
  let callbacks: TrackerCallbacks<T> | undefined
  let wsCallback: ((raw: unknown) => void) | null = null
  let fallbackTimer: ReturnType<typeof setTimeout> | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let connectionCheckTimer: ReturnType<typeof setInterval> | null = null
  let pollStart = 0
  let stopped = false

  // ── Handle incoming data (from WS or poll) ──────────────
  function handleData(d: T): void {
    data.value = d
    callbacks?.onProgress?.(d)

    const terminal = config.isTerminal(d)
    if (terminal === 'completed') {
      callbacks?.onComplete?.(d)
      stopTracking()
    } else if (terminal === 'failed') {
      const code = config.getErrorCode?.(d) ?? null
      callbacks?.onError?.(config.getError(d) || 'Failed', code)
      stopTracking()
    }
  }

  // ── WebSocket path ──────────────────────────────────────
  function handleWsMessage(raw: unknown): void {
    handleData(raw as T)
  }

  // ── Polling fallback ────────────────────────────────────
  async function poll(): Promise<void> {
    if (stopped || !currentId) return
    // Capture the polled id; the tracker may be swapped or stopped
    // while the request is in flight. Same guard as fetchInitialState
    // — without it, a stale response would feed handleData with the
    // new tracker's callbacks.
    const requestId = currentId
    try {
      const { data: responseData } = await api.get<T>(
        config.pollEndpoint(requestId),
      )
      if (stopped || currentId !== requestId) return
      handleData(responseData)

      // If handleData called stopTracking (terminal state), don't reschedule
      if (stopped) return

      if (Date.now() - pollStart > pollTimeoutMs) {
        callbacks?.onError?.('Polling timed out')
        stopTracking()
        return
      }
      pollTimer = setTimeout(poll, pollIntervalMs)
    } catch (err) {
      // 404 means the backend's in-memory entry is gone — either
      // because the job was reaped after a successful terminal state
      // (5-min TTL) OR because the backend restarted and wiped the
      // in-memory ``_job_store`` while the owning DB row still
      // carries the now-dead ``job_id``. In both cases the in-memory
      // tracker can't recover useful state; the DB row is the source
      // of truth and a fresh ``loadDesigns`` / ``fetchBUD`` will
      // reflect it. Stop tracking silently — firing ``onError``
      // would trigger callers like ``BUDDesignPanel.trackDesignJob``
      // to reload designs and re-track, which on a stuck-generating
      // row produces another 404 → another reload → a request loop.
      if ((err as AxiosError).response?.status === 404) {
        stopTracking()
        return
      }
      callbacks?.onError?.('Failed to check status')
      stopTracking()
    }
  }

  function startPollingIfNeeded(): void {
    if (stopped || !currentId) return
    if (pollTimer) return // already polling
    // `pollAlongsideWs` flips this between two modes:
    //   * true  — always-on belt-and-suspenders. Necessary for trackers
    //             like the scan whose terminal event can be published
    //             before the WS subscribe propagates (the UI would
    //             otherwise get stuck at the last received progress).
    //   * false — fallback only. Trackers whose backend state is
    //             short-lived (e.g. jobs cleaned up after 5 min) would
    //             otherwise emit spurious 404-backed "Failed to check
    //             status" errors once the entry is reaped.
    if (!pollAlongsideWs && isConnected()) return
    pollStart = Date.now()
    poll()
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  // ── Public API ──────────────────────────────────────────

  /** One-shot fetch so the UI shows current state immediately on subscribe. */
  async function fetchInitialState(): Promise<void> {
    if (stopped || !currentId) return
    // Capture the id we're fetching for; if startTracking gets called
    // again (different id) while this request is in flight, the
    // response is stale and must not invoke callbacks. Without this
    // guard, a terminal seed (e.g. a job that became "cancelled"
    // between cancel-click and seed return) would fire onError on
    // the *new* tracker's callbacks — which the design panel uses to
    // call ``loadDesigns()`` → ``trackDesignJob()`` → another seed
    // fetch, producing an unbounded request loop.
    const requestId = currentId
    try {
      const { data: responseData } = await api.get<T>(
        config.pollEndpoint(requestId),
      )
      if (stopped || currentId !== requestId) return
      // Only apply if we haven't received a WS message yet (avoid overwriting fresher data)
      if (data.value === null) {
        handleData(responseData)
      }
    } catch {
      // Non-critical — WS or polling will pick up state
    }
  }

  function startTracking(id: string, cbs?: TrackerCallbacks<T>): void {
    stopTracking()
    stopped = false
    currentId = id
    callbacks = cbs
    isActive.value = true

    // Subscribe via WebSocket
    const topic = `${config.topicPrefix}:${id}`
    wsCallback = handleWsMessage
    subscribe(topic, wsCallback)

    // Immediately fetch current state so the UI doesn't wait for the next stage transition.
    // Skipped for pure WS-driven trackers (jobs) whose backend state vanishes after terminal.
    if (fetchInitialStateViaRest) {
      fetchInitialState()
    }

    // Fallback: start polling if WS doesn't connect in time
    fallbackTimer = setTimeout(startPollingIfNeeded, fallbackDelayMs)

    // Periodic health check:
    //   pollAlongsideWs=true  — ensure polling is always running;
    //                           restart if it died.
    //   pollAlongsideWs=false — kick polling on when the WS drops,
    //                           stop it again when the WS recovers.
    connectionCheckTimer = setInterval(() => {
      if (stopped) {
        if (connectionCheckTimer) clearInterval(connectionCheckTimer)
        return
      }
      if (pollAlongsideWs) {
        if (!pollTimer) {
          pollStart = Date.now()
          poll()
        }
        return
      }
      if (!isConnected() && !pollTimer) {
        pollStart = Date.now()
        poll()
      } else if (isConnected() && pollTimer) {
        stopPolling()
      }
    }, connectionCheckMs)
  }

  function stopTracking(): void {
    stopped = true
    isActive.value = false

    if (currentId && wsCallback) {
      unsubscribe(`${config.topicPrefix}:${currentId}`, wsCallback)
    }
    wsCallback = null

    if (fallbackTimer) {
      clearTimeout(fallbackTimer)
      fallbackTimer = null
    }
    stopPolling()
    if (connectionCheckTimer) {
      clearInterval(connectionCheckTimer)
      connectionCheckTimer = null
    }
    currentId = null
    callbacks = undefined
  }

  onUnmounted(stopTracking)

  return { data, isActive, startTracking, stopTracking }
}
