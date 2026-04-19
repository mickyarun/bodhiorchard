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
  })

  return {
    status: tracker.data,
    isActive: tracker.isActive,
    startTracking: (jobId: string, cbs?: TrackerCallbacks<JobStatusRead>) =>
      tracker.startTracking(jobId, cbs),
    stopTracking: tracker.stopTracking,
  }
}
