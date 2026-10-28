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

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User } from '@/types'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'
import { forgetReturnTo } from '@/utils/returnTo'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('bodhiorchard_token'))
  const loginError = ref<string | null>(null)
  const mustChangePassword = ref(false)

  const isAuthenticated = computed(() => !!token.value)

  // The axios 401-refresh interceptor writes new tokens to localStorage and
  // fires this event so we can update our reactive ref. Without the listener,
  // `token.value` would stay stale after an automatic refresh (any consumer
  // reading `authStore.token` would send the old expired JWT to services like
  // the Colyseus OrgRoom, which rejects it via onAuth).
  window.addEventListener('glideship:token-refreshed', ((event: Event) => {
    const detail = (event as CustomEvent<{ accessToken: string }>).detail
    if (detail?.accessToken) {
      token.value = detail.accessToken
    }
  }) as EventListener)

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
      localStorage.setItem('bodhiorchard_token', response.data.access_token)
      if (response.data.refresh_token) {
        localStorage.setItem('bodhiorchard_refresh_token', response.data.refresh_token)
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
      const status = (err as { response?: { status?: number } } | null)?.response?.status
      // A 422 carries FastAPI's validation list; extractApiError turns it
      // into sentences rather than showing the raw JSON.
      loginError.value = status === 401
        ? 'Invalid email or password.'
        : extractApiError(err, 'Login failed. Please try again.')
      return false
    }
  }

  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem('bodhiorchard_token')
    localStorage.removeItem('bodhiorchard_refresh_token')
    // A message from the last sign-in mustn't greet the next visit to login.
    loginError.value = null
    // Never send whoever signs in next to this person's page.
    forgetReturnTo()
  }

  async function fetchUser(): Promise<void> {
    if (!token.value) return
    const response = await api.get('/v1/auth/me')
    user.value = response.data
  }

  /** Show a new (or removed) photo of the signed-in user straight away. */
  function setAvatarUrl(avatarUrl: string | null): void {
    if (user.value) user.value = { ...user.value, avatar_url: avatarUrl }
  }

  async function changePassword(newPassword: string): Promise<string | null> {
    try {
      await api.post('/v1/auth/change-password', { new_password: newPassword })
      mustChangePassword.value = false
      return null
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } } | null)?.response?.status
      return status === 401
        ? 'Session expired. Please log in again.'
        : extractApiError(err, 'Failed to change password.')
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
    setAvatarUrl,
    changePassword,
  }
})
