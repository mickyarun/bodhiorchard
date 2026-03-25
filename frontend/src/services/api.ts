import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'
import type { ApiError } from '@/types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('flowdev_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

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

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiError>) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean }

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
    const refreshToken = localStorage.getItem('flowdev_refresh_token')
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

      localStorage.setItem('flowdev_token', data.access_token)
      localStorage.setItem('flowdev_refresh_token', data.refresh_token)

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
  localStorage.removeItem('flowdev_token')
  localStorage.removeItem('flowdev_refresh_token')
  // Only redirect if not already on login/setup pages
  if (!window.location.pathname.startsWith('/login') && !window.location.pathname.startsWith('/setup')) {
    window.location.href = '/login'
  }
}

export default api
