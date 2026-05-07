// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Extract a user-friendly error message from an Axios error response.
 *
 * Returns permission-specific messages for 403, the server's detail
 * string when available, or the provided fallback for unknown errors.
 */
export function extractApiError(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as {
      response?: { status?: number; data?: { detail?: unknown } }
    }
    const detail = axiosErr.response?.data?.detail
    const detailString = stringifyDetail(detail)
    if (axiosErr.response?.status === 403) {
      return detailString || 'Insufficient permissions.'
    }
    return detailString || fallback
  }
  return 'Network error. Please check your connection.'
}

/**
 * Coerce a FastAPI ``detail`` field to a string. Handles the legacy
 * shape (plain string) and the typed envelope used by Phase J's
 * credential validation (``{ error: "...", message: "..." }``) so
 * callers can pattern-match on the JSON shape downstream without
 * losing the structured payload to ``[object Object]`` coercion.
 */
function stringifyDetail(detail: unknown): string {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (typeof detail === 'object') {
    try {
      return JSON.stringify(detail)
    } catch {
      return ''
    }
  }
  return String(detail)
}
