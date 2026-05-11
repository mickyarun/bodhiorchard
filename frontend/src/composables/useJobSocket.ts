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
    getErrorCode: (d) => d.errorCode ?? null,
    getResult: (d) => d.result,
    pollIntervalMs: 1000,
    pollTimeoutMs: 660_000, // 11 min — must exceed backend max job timeout (600s)
    // WS-primary tracking. The subscribe-vs-publish race (WS subscribe
    // landing after the worker already published the terminal event) is
    // closed by `fetchInitialStateViaRest`: one REST seed at
    // `startTracking` returns the current state, so a job that already
    // finished fires `onComplete` immediately. The seed swallows errors,
    // so a job whose 5-min TTL already reaped doesn't surface as a
    // spurious "Failed to check status". After the seed, the WS is the
    // source of truth; the tracker's connection-health timer (5 s) auto-
    // resumes polling if the WS drops mid-job and stops it on reconnect.
    //
    // Differs from `useScanSocket`, which keeps `pollAlongsideWs: true`
    // because scans run for hours, state is durable in Redis, and the
    // cost of missing a terminal event is high. For short-lived jobs the
    // 1-Hz poll was pure log noise.
    fetchInitialStateViaRest: true,
    pollAlongsideWs: false,
  })

  return {
    status: tracker.data,
    isActive: tracker.isActive,
    startTracking: (jobId: string, cbs?: TrackerCallbacks<JobStatusRead>) =>
      tracker.startTracking(jobId, cbs),
    stopTracking: tracker.stopTracking,
  }
}
