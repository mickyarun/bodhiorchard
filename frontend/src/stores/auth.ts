import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '@/types'
import api from '@/services/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('bodhigrove_token'))
  const loginError = ref<string | null>(null)
  const mustChangePassword = ref(false)

  const isAuthenticated = computed(() => !!token.value)

  async function login(email: string, password: string, orgSlug: string): Promise<boolean> {
    loginError.value = null
    mustChangePassword.value = false
    try {
      const response = await api.post('/v1/auth/login', {
        email,
        password,
        org_slug: orgSlug,
      })
      token.value = response.data.access_token
      localStorage.setItem('bodhigrove_token', response.data.access_token)
      if (response.data.refresh_token) {
        localStorage.setItem('bodhigrove_refresh_token', response.data.refresh_token)
      }
      mustChangePassword.value = response.data.must_change_password === true
      // Fetch user profile — don't block login but surface the error
      try {
        await fetchUser()
      } catch {
        loginError.value = 'Logged in but failed to load profile. Please refresh.'
      }
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
    localStorage.removeItem('bodhigrove_token')
    localStorage.removeItem('bodhigrove_refresh_token')
  }

  async function fetchUser(): Promise<void> {
    if (!token.value) return
    const response = await api.get('/v1/auth/me')
    user.value = response.data
  }

  async function changePassword(newPassword: string): Promise<string | null> {
    try {
      await api.post('/v1/auth/change-password', { new_password: newPassword })
      mustChangePassword.value = false
      return null
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } }
        if (axiosErr.response?.status === 401) {
          return 'Session expired. Please log in again.'
        }
        return axiosErr.response?.data?.detail || 'Failed to change password.'
      }
      return 'Network error. Please check your connection.'
    }
  }

  return {
    user,
    token,
    loginError,
    mustChangePassword,
    isAuthenticated,
    login,
    logout,
    fetchUser,
    changePassword,
  }
})
