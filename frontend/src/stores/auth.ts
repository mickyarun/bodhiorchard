import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '@/types'
import api from '@/services/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('flowdev_token'))

  const isAuthenticated = computed(() => !!token.value)

  async function login(email: string, password: string): Promise<boolean> {
    try {
      const response = await api.post('/auth/login', { email, password })
      token.value = response.data.token
      user.value = response.data.user
      localStorage.setItem('flowdev_token', response.data.token)
      return true
    } catch {
      return false
    }
  }

  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem('flowdev_token')
  }

  async function fetchUser(): Promise<void> {
    if (!token.value) return
    try {
      const response = await api.get('/auth/me')
      user.value = response.data
    } catch {
      logout()
    }
  }

  return {
    user,
    token,
    isAuthenticated,
    login,
    logout,
    fetchUser,
  }
})
