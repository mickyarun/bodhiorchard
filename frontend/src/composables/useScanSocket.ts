// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
  error: string | null
}

export function useScanSocket() {
  const tracker = useRealtimeTracker<ScanStatusData>({
    topicPrefix: 'scan',
    pollEndpoint: (id) => `/v1/skills/scan/${id}/status`,
    isTerminal: (d) =>
      d.status === 'completed' ? 'completed' : d.status === 'failed' ? 'failed' : null,
    getError: (d) => d.error || null,
    pollIntervalMs: 2000,
    pollTimeoutMs: 1_800_000, // 30 min — scans can be long
    // Scan progress lives in Redis for 30 min; the subscribe →
    // first-publish race can still drop `scan_complete` (backend logs
    // `event_bus_no_subscribers` right before the terminal event),
    // leaving the UI stuck at the last received percent. Polling
    // alongside the WS is cheap insurance.
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
