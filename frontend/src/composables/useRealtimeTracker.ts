// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
 *     pollEndpoint: (id) => `/v1/skills/scan/${id}/status`,
 *     isTerminal: (d) => d.status === 'completed' ? 'completed' : d.status === 'failed' ? 'failed' : null,
 *     getError: (d) => d.error || null,
 *   })
 */
import { ref, onUnmounted } from 'vue'
import { subscribe, unsubscribe, isConnected } from '@/services/socket'
import api from '@/services/api'

export interface TrackerCallbacks<T> {
  onProgress?: (data: T) => void
  onComplete?: (data: T) => void
  onError?: (error: string) => void
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
  /** Extracts result from data (optional, for job-style tracking) */
  getResult?: (data: T) => unknown
  /** Polling interval in ms (default: 2000) */
  pollIntervalMs?: number
  /** Max polling duration in ms (default: 1_800_000 = 30 min) */
  pollTimeoutMs?: number
  /** Delay before falling back to polling (default: 3000) */
  fallbackDelayMs?: number
  /** Interval for WS health checks in ms (default: 5000) */
  connectionCheckMs?: number
}

export function useRealtimeTracker<T>(config: TrackerConfig<T>) {
  const data = ref<T | null>(null)
  const isActive = ref(false)

  const pollIntervalMs = config.pollIntervalMs ?? 2000
  const pollTimeoutMs = config.pollTimeoutMs ?? 1_800_000
  const fallbackDelayMs = config.fallbackDelayMs ?? 3000
  const connectionCheckMs = config.connectionCheckMs ?? 5000

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
      callbacks?.onError?.(config.getError(d) || 'Failed')
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
    try {
      const { data: responseData } = await api.get<T>(
        config.pollEndpoint(currentId),
      )
      handleData(responseData)

      // If handleData called stopTracking (terminal state), don't reschedule
      if (stopped) return

      if (Date.now() - pollStart > pollTimeoutMs) {
        callbacks?.onError?.('Polling timed out')
        stopTracking()
        return
      }
      pollTimer = setTimeout(poll, pollIntervalMs)
    } catch {
      callbacks?.onError?.('Failed to check status')
      stopTracking()
    }
  }

  function startPollingIfNeeded(): void {
    if (stopped || !currentId) return
    if (pollTimer) return // already polling
    // We used to skip polling when the WS was "connected", but the topic
    // subscribe → first-publish race can still drop a terminal event (the
    // backend publishes `scan_complete` before the client's subscribe has
    // propagated, and the UI stays stuck in "scanning"). Polling is cheap
    // (a single GET every `pollIntervalMs`), idempotent with `handleData`,
    // and stops the moment a terminal state arrives — so run it as a
    // belt-and-suspenders alongside the WS rather than only on fallback.
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
    try {
      const { data: responseData } = await api.get<T>(
        config.pollEndpoint(currentId),
      )
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

    // Immediately fetch current state so the UI doesn't wait for the next stage transition
    fetchInitialState()

    // Fallback: start polling if WS doesn't connect in time
    fallbackTimer = setTimeout(startPollingIfNeeded, fallbackDelayMs)

    // Periodic health check: handles WS dropping mid-tracking
    connectionCheckTimer = setInterval(() => {
      if (stopped) {
        if (connectionCheckTimer) clearInterval(connectionCheckTimer)
        return
      }
      if (!isConnected() && !pollTimer) {
        // WS dropped — start polling
        pollStart = Date.now()
        poll()
      } else if (isConnected() && pollTimer) {
        // WS reconnected — stop polling, WS takes over
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
