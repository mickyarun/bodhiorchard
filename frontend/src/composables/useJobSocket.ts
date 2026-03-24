/**
 * Job-specific composable that pushes status via WebSocket with
 * automatic polling fallback.
 *
 * Drop-in replacement for useJobPoller — same callback interface:
 *   const { status, isActive, startTracking, stopTracking } = useJobSocket()
 *   startTracking(jobId, { onProgress, onComplete, onError })
 */
import { ref, onUnmounted } from 'vue'
import { subscribe, unsubscribe, isConnected } from '@/services/socket'
import api from '@/services/api'
import type { JobStatusRead } from '@/types'

interface JobCallbacks {
  onProgress?: (status: JobStatusRead) => void
  onComplete?: (result: unknown) => void
  onError?: (error: string) => void
}

const FALLBACK_DELAY_MS = 3000 // wait before falling back to polling
const POLL_INTERVAL_MS = 1000
const POLL_TIMEOUT_MS = 660_000 // 11 min — must exceed backend's max job timeout (600s)

export function useJobSocket() {
  const status = ref<JobStatusRead | null>(null)
  const isActive = ref(false)

  let currentJobId: string | null = null
  let callbacks: JobCallbacks | undefined
  let wsCallback: ((data: unknown) => void) | null = null
  let fallbackTimer: ReturnType<typeof setTimeout> | null = null
  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let pollStart = 0
  let stopped = false

  // ── WebSocket path ──────────────────────────────────────
  function handleWsMessage(data: unknown): void {
    const jobData = data as JobStatusRead
    status.value = jobData
    callbacks?.onProgress?.(jobData)

    if (jobData.state === 'completed') {
      callbacks?.onComplete?.(jobData.result)
      stopTracking()
    } else if (jobData.state === 'failed') {
      callbacks?.onError?.(jobData.error || 'Job failed')
      stopTracking()
    }
  }

  // ── Polling fallback ────────────────────────────────────
  async function poll(): Promise<void> {
    if (stopped || !currentJobId) return
    try {
      const { data } = await api.get<JobStatusRead>(`/v1/jobs/${currentJobId}/status`)
      status.value = data
      callbacks?.onProgress?.(data)

      if (data.state === 'completed') {
        callbacks?.onComplete?.(data.result)
        stopTracking()
        return
      }
      if (data.state === 'failed') {
        callbacks?.onError?.(data.error || 'Job failed')
        stopTracking()
        return
      }
      if (Date.now() - pollStart > POLL_TIMEOUT_MS) {
        callbacks?.onError?.('Job polling timed out')
        stopTracking()
        return
      }
      pollTimer = setTimeout(poll, POLL_INTERVAL_MS)
    } catch {
      callbacks?.onError?.('Failed to check job status')
      stopTracking()
    }
  }

  function startPollingFallback(): void {
    if (stopped || !currentJobId) return
    // Only fall back if WS isn't connected by now
    if (isConnected()) return
    pollStart = Date.now()
    poll()
  }

  // ── Public API ──────────────────────────────────────────

  function startTracking(jobId: string, cbs?: JobCallbacks): void {
    stopTracking()
    stopped = false
    currentJobId = jobId
    callbacks = cbs
    isActive.value = true

    // Subscribe via WebSocket
    const topic = `job:${jobId}`
    wsCallback = handleWsMessage
    subscribe(topic, wsCallback)

    // Schedule polling fallback if WS doesn't connect in time
    fallbackTimer = setTimeout(startPollingFallback, FALLBACK_DELAY_MS)
  }

  function stopTracking(): void {
    stopped = true
    isActive.value = false

    if (currentJobId && wsCallback) {
      unsubscribe(`job:${currentJobId}`, wsCallback)
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
    currentJobId = null
    callbacks = undefined
  }

  onUnmounted(stopTracking)

  return { status, isActive, startTracking, stopTracking }
}
