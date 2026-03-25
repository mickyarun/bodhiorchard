/**
 * Scan-specific composable that pushes status via WebSocket with
 * automatic polling fallback.
 *
 * Modeled on useJobSocket — same WS+polling pattern adapted for
 * the scan status shape (progressPct, featuresIndexed, etc.).
 *
 * Usage:
 *   const { scanData, isActive, startTracking, stopTracking } = useScanSocket()
 *   startTracking(scanId, { onProgress, onComplete, onError })
 */
import { ref, onUnmounted } from 'vue'
import { subscribe, unsubscribe, isConnected } from '@/services/socket'
import api from '@/services/api'

export interface ScanStatusData {
  scanId: string
  status: string
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

interface ScanCallbacks {
  onProgress?: (data: ScanStatusData) => void
  onComplete?: (data: ScanStatusData) => void
  onError?: (error: string) => void
}

const FALLBACK_DELAY_MS = 3000
const POLL_INTERVAL_MS = 2000
const POLL_TIMEOUT_MS = 1_800_000 // 30 min — scans can be long

export function useScanSocket() {
  const scanData = ref<ScanStatusData | null>(null)
  const isActive = ref(false)

  let currentScanId: string | null = null
  let callbacks: ScanCallbacks | undefined
  let wsCallback: ((data: unknown) => void) | null = null
  let fallbackTimer: ReturnType<typeof setTimeout> | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let pollStart = 0
  let stopped = false

  // ── WebSocket path ──────────────────────────────────────
  function handleWsMessage(data: unknown): void {
    const d = data as ScanStatusData
    scanData.value = d
    callbacks?.onProgress?.(d)

    if (d.status === 'completed') {
      callbacks?.onComplete?.(d)
      stopTracking()
    } else if (d.status === 'failed') {
      callbacks?.onError?.(d.error || 'Scan failed')
      stopTracking()
    }
  }

  // ── Polling fallback ────────────────────────────────────
  async function poll(): Promise<void> {
    if (stopped || !currentScanId) return
    try {
      const { data } = await api.get<ScanStatusData>(
        `/v1/skills/scan/${currentScanId}/status`,
      )
      scanData.value = data
      callbacks?.onProgress?.(data)

      if (data.status === 'completed') {
        callbacks?.onComplete?.(data)
        stopTracking()
        return
      }
      if (data.status === 'failed') {
        callbacks?.onError?.(data.error || 'Scan failed')
        stopTracking()
        return
      }
      if (Date.now() - pollStart > POLL_TIMEOUT_MS) {
        callbacks?.onError?.('Scan polling timed out')
        stopTracking()
        return
      }
      pollTimer = setTimeout(poll, POLL_INTERVAL_MS)
    } catch {
      callbacks?.onError?.('Failed to check scan status')
      stopTracking()
    }
  }

  function startPollingFallback(): void {
    if (stopped || !currentScanId) return
    if (isConnected()) return
    pollStart = Date.now()
    poll()
  }

  // ── Public API ──────────────────────────────────────────

  function startTracking(scanId: string, cbs?: ScanCallbacks): void {
    stopTracking()
    stopped = false
    currentScanId = scanId
    callbacks = cbs
    isActive.value = true

    const topic = `scan:${scanId}`
    wsCallback = handleWsMessage
    subscribe(topic, wsCallback)

    // Fall back to polling if WS doesn't connect in time
    fallbackTimer = setTimeout(startPollingFallback, FALLBACK_DELAY_MS)
  }

  function stopTracking(): void {
    stopped = true
    isActive.value = false

    if (currentScanId && wsCallback) {
      unsubscribe(`scan:${currentScanId}`, wsCallback)
    }
    wsCallback = null

    if (fallbackTimer) {
      clearTimeout(fallbackTimer)
      fallbackTimer = null
    }
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
    currentScanId = null
    callbacks = undefined
  }

  onUnmounted(stopTracking)

  return { scanData, isActive, startTracking, stopTracking }
}
