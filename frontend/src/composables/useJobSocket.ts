// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Job-specific composable that pushes status via WebSocket with
 * automatic polling fallback.
 *
 * Thin wrapper around useRealtimeTracker — same callback interface:
 *   const { status, isActive, startTracking, stopTracking } = useJobSocket()
 *   startTracking(jobId, { onProgress, onComplete, onError })
 */
import { useRealtimeTracker } from '@/composables/useRealtimeTracker'
import type { TrackerCallbacks } from '@/composables/useRealtimeTracker'
import type { JobStatusRead } from '@/types'

export function useJobSocket() {
  const tracker = useRealtimeTracker<JobStatusRead>({
    topicPrefix: 'job',
    pollEndpoint: (id) => `/v1/jobs/${id}/status`,
    isTerminal: (d) =>
      d.state === 'completed' ? 'completed' : d.state === 'failed' ? 'failed' : null,
    getError: (d) => d.error || null,
    getResult: (d) => d.result,
    pollIntervalMs: 1000,
    pollTimeoutMs: 660_000, // 11 min — must exceed backend max job timeout (600s)
    // Jobs are WS-native but the WS subscribe can land AFTER the worker
    // has already published the terminal event — the frontend sees the
    // running banner forever because `onComplete` never fires. Keep
    // polling running alongside the WS (1 Hz) as a safety net; the
    // tracker handles 404-after-cleanup silently so there's no spurious
    // "Failed to check status" when the 5-min TTL reaps the in-memory
    // entry. Same pattern `useScanSocket` uses for the identical race.
    fetchInitialStateViaRest: false,
    pollAlongsideWs: true,
  })

  return {
    status: tracker.data,
    isActive: tracker.isActive,
    startTracking: (jobId: string, cbs?: TrackerCallbacks<JobStatusRead>) =>
      tracker.startTracking(jobId, cbs),
    stopTracking: tracker.stopTracking,
  }
}
