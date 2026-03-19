import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '@/types'
import api from '@/services/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('flowdev_token'))
  const loginError = ref<string | null>(null)

  const isAuthenticated = computed(() => !!token.value)

  async function login(email: string, password: string, orgSlug: string): Promise<boolean> {
    loginError.value = null
    try {
      const response = await api.post('/v1/auth/login', {
        email,
        password,
        org_slug: orgSlug,
      })
      token.value = response.data.access_token
      localStorage.setItem('flowdev_token', response.data.access_token)
      if (response.data.refresh_token) {
        localStorage.setItem('flowdev_refresh_token', response.data.refresh_token)
      }
      // Fetch user profile but don't break login if it fails
      try { await fetchUser() } catch { /* token is valid, profile fetch can retry later */ }
      return true
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
        if (axiosErr.response?.status === 401) {
          loginError.value = 'Invalid email or password.'
        } else {
          loginError.value = axiosErr.response?.data?.detail || 'Login failed. Please try again.'
        }
      } else {
        loginError.value = 'Network error. Please check your connection.'
      }
      return false
    }
  }

  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem('flowdev_token')
    localStorage.removeItem('flowdev_refresh_token')
  }

  async function fetchUser(): Promise<void> {
    if (!token.value) return
    const response = await api.get('/v1/auth/me')
    user.value = response.data
  }

  return {
    user,
    token,
    loginError,
    isAuthenticated,
    login,
    logout,
    fetchUser,
  }
})
