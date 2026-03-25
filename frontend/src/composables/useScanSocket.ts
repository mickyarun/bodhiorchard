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
  })

  return {
    scanData: tracker.data,
    isActive: tracker.isActive,
    startTracking: (scanId: string, cbs?: TrackerCallbacks<ScanStatusData>) =>
      tracker.startTracking(scanId, cbs),
    stopTracking: tracker.stopTracking,
  }
}
