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
