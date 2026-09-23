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

import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from '@/types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

/**
 * Per-request header fixups. Exported so the FormData rule can be
 * asserted against axios's real ``transformRequest`` in tests.
 *
 * The instance default above is ``application/json``, which axios does
 * NOT treat as a passive default: ``transformRequest`` branches on it,
 * and for a FormData body with a JSON content-type it rewrites the form
 * into JSON via ``formDataToJSON`` — silently dropping every File, so
 * the backend sees no multipart part at all and rejects the request as
 * ``{"loc": ["body", "file"], "msg": "Field required"}``.
 *
 * Clearing the header for FormData bodies keeps the form intact, and
 * axios's ``resolveConfig`` then lets the browser supply
 * ``multipart/form-data`` with the boundary it alone can generate.
 * Doing it here means no upload call site has to remember the rule.
 */
export function applyRequestHeaders(
  config: InternalAxiosRequestConfig,
): InternalAxiosRequestConfig {
  const token = localStorage.getItem('bodhiorchard_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    config.headers.delete('Content-Type')
  }
  return config
}

api.interceptors.request.use(applyRequestHeaders)

// Track whether a token refresh is in progress to avoid multiple simultaneous refreshes
let isRefreshing = false
let failedQueue: Array<{
  resolve: (token: string) => void
  reject: (error: unknown) => void
}> = []

function processQueue(error: unknown, token: string | null): void {
  failedQueue.forEach(({ resolve, reject }) => {
    if (token) {
      resolve(token)
    } else {
      reject(error)
    }
  })
  failedQueue = []
}

/**
 * Replace a Blob error body with its parsed JSON, in place.
 *
 * A request made with ``responseType: 'blob'`` gets a Blob back even on
 * failure, so ``error.response.data`` holds an unparsed Blob rather than
 * the backend's ``{"detail": "..."}``. Everything downstream reads
 * ``.detail`` — the password-change branch below, ``extractApiError``,
 * the attachment tile's error text — and silently degrades to a generic
 * "Request failed with status code 404" instead of the real reason.
 *
 * Normalising here means blob callers need no special handling, and a
 * 403 on a download still reaches the change-password redirect.
 */
async function parseBlobErrorBody(error: AxiosError): Promise<void> {
  const response = error.response
  if (!response || !(response.data instanceof Blob)) return
  try {
    response.data = JSON.parse(await response.data.text())
  } catch {
    // Not JSON — an nginx HTML error page, or a truncated stream. Leave
    // the Blob alone; every consumer already handles a missing detail.
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

    // Deliberately skipped for 401s. Everything between here and the
    // `isRefreshing` check below is synchronous, which is what makes
    // concurrent 401s safe: the first one flips the flag before it
    // yields, so the rest queue instead of each starting their own
    // token refresh. Awaiting `Blob.text()` here would insert a yield
    // ahead of that check — and concurrent blob 401s are easy to hit,
    // since a bug detail panel fires one request per image tile at
    // once. The cost is that a 401 keeps axios's generic message, which
    // is no loss: its body says "Not authenticated", and the user is
    // being refreshed or redirected rather than shown the text.
    if (error.response?.status !== 401) {
      await parseBlobErrorBody(error)
    }

    // Redirect to change-password on 403 "Password change required"
    const responseData = error.response?.data as Record<string, unknown> | undefined
    if (
      error.response?.status === 403
      && responseData?.detail === 'Password change required'
      && !window.location.pathname.startsWith('/change-password')
    ) {
      window.location.href = '/change-password'
      return Promise.reject(error)
    }

    // Only intercept 401s for non-auth endpoints (don't retry login/refresh failures)
    if (
      error.response?.status !== 401
      || !originalRequest
      || originalRequest._retry
      || originalRequest.url?.includes('/auth/login')
      || originalRequest.url?.includes('/auth/refresh')
    ) {
      return Promise.reject(error)
    }

    // Try to refresh the token
    const refreshToken = localStorage.getItem('bodhiorchard_refresh_token')
    if (!refreshToken) {
      clearAuthAndRedirect()
      return Promise.reject(error)
    }

    if (isRefreshing) {
      // Another refresh is in progress — queue this request
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject })
      }).then((token) => {
        originalRequest.headers.Authorization = `Bearer ${token}`
        return api(originalRequest)
      })
    }

    isRefreshing = true
    originalRequest._retry = true

    try {
      const { data } = await axios.post(
        `${api.defaults.baseURL}/v1/auth/refresh`,
        { refresh_token: refreshToken },
        { headers: { 'Content-Type': 'application/json' } },
      )

      localStorage.setItem('bodhiorchard_token', data.access_token)
      localStorage.setItem('bodhiorchard_refresh_token', data.refresh_token)

      // Notify listeners (e.g. Pinia auth store) that the token was refreshed.
      // Window-event pattern avoids a circular import between this file and
      // the auth store — stores can't import from here, but they can listen.
      // Consumers like PlayCanvasCanvas read localStorage directly for the
      // hot path, so this event is belt-and-suspenders for anyone caching
      // the token in a reactive ref.
      window.dispatchEvent(new CustomEvent('bodhiorchard:token-refreshed', {
        detail: { accessToken: data.access_token },
      }))

      processQueue(null, data.access_token)

      originalRequest.headers.Authorization = `Bearer ${data.access_token}`
      return api(originalRequest)
    } catch (refreshError) {
      processQueue(refreshError, null)
      clearAuthAndRedirect()
      return Promise.reject(refreshError)
    } finally {
      isRefreshing = false
    }
  },
)

function clearAuthAndRedirect(): void {
  localStorage.removeItem('bodhiorchard_token')
  localStorage.removeItem('bodhiorchard_refresh_token')
  // Only redirect if not already on login/setup pages
  if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/setup')) {
    window.location.href = '/login'
  }
}

export default api
