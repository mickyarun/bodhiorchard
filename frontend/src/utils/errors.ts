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
