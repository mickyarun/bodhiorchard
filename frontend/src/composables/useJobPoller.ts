/**
 * Reusable composable for polling async job status.
 *
 * Usage:
 *   const { status, isPolling, startPolling, stopPolling } = useJobPoller()
 *   await startPolling(jobId, { onProgress, onComplete, onError })
 */
import { ref, onUnmounted } from 'vue'
import api from '@/services/api'
import type { JobStatusRead } from '@/types'

interface PollingCallbacks {
  onProgress?: (status: JobStatusRead) => void
  onComplete?: (result: unknown) => void
  onError?: (error: string) => void
}

export function useJobPoller(intervalMs = 1000, timeoutMs = 660_000) {
  const status = ref<JobStatusRead | null>(null)
  const isPolling = ref(false)
  let timer: ReturnType<typeof setTimeout> | null = null
  let aborted = false

  async function startPolling(jobId: string, callbacks?: PollingCallbacks): Promise<void> {
    aborted = false
    isPolling.value = true
    const start = Date.now()

    const poll = async () => {
      if (aborted) return

      try {
        const { data } = await api.get<JobStatusRead>(`/v1/jobs/${jobId}/status`)
        status.value = data
        callbacks?.onProgress?.(data)

        if (data.state === 'completed') {
          isPolling.value = false
          callbacks?.onComplete?.(data.result)
          return
        }
        if (data.state === 'failed') {
          isPolling.value = false
          callbacks?.onError?.(data.error || 'Job failed')
          return
        }
        if (Date.now() - start > timeoutMs) {
          isPolling.value = false
          callbacks?.onError?.('Job polling timed out')
          return
        }

        timer = setTimeout(poll, intervalMs)
      } catch {
        isPolling.value = false
        callbacks?.onError?.('Failed to check job status')
      }
    }

    await poll()
  }

  function stopPolling(): void {
    aborted = true
    isPolling.value = false
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  // Auto-cleanup when component unmounts
  onUnmounted(stopPolling)

  return { status, isPolling, startPolling, stopPolling }
}
