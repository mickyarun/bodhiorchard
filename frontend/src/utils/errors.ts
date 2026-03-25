/**
 * Extract a user-friendly error message from an Axios error response.
 *
 * Returns permission-specific messages for 403, the server's detail
 * string when available, or the provided fallback for unknown errors.
 */
export function extractApiError(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
    if (axiosErr.response?.status === 403) {
      return axiosErr.response?.data?.detail || 'Insufficient permissions.'
    }
    return axiosErr.response?.data?.detail || fallback
  }
  return 'Network error. Please check your connection.'
}
