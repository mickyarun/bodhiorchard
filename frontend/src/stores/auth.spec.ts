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
 * Sign-in state: what a login keeps, the message each failure shows,
 * what sign-out forgets, and the token the axios refresh hands over.
 * ``.spec.ts`` for jsdom's localStorage.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { rememberReturnTo, takeReturnTo } from '@/utils/returnTo'

const get = vi.mocked(api.get)
const post = vi.mocked(api.post)
const ME = { id: 'u1', email: 'ana@example.com', permissions: ['buds:view'] }

function httpError(status: number, detail?: unknown): Error {
  return Object.assign(new Error(`status ${status}`), { response: { status, data: { detail } } })
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  get.mockReset()
  post.mockReset()
  get.mockResolvedValue({ data: ME })
  setActivePinia(createPinia())
})

describe('login', () => {
  it('keeps both tokens, loads the profile and signs in', async () => {
    post.mockResolvedValue({ data: { access_token: 'a1', refresh_token: 'r1' } })
    const auth = useAuthStore()

    expect(await auth.login('ana@example.com', 'secret-pass', 'acme')).toBe(true)

    expect(post).toHaveBeenCalledWith('/v1/auth/login', {
      email: 'ana@example.com', password: 'secret-pass', org_slug: 'acme',
    })
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.token).toBe('a1')
    expect(localStorage.getItem('bodhiorchard_token')).toBe('a1')
    expect(localStorage.getItem('bodhiorchard_refresh_token')).toBe('r1')
    expect(get).toHaveBeenCalledWith('/v1/auth/me')
    expect(auth.user).toEqual(ME)
    expect(auth.mustChangePassword).toBe(false)
    expect(auth.loginError).toBeNull()
  })

  it('flags an account that must change its password first', async () => {
    post.mockResolvedValue({ data: { access_token: 'a1', must_change_password: true } })
    const auth = useAuthStore()
    expect(await auth.login('ana@example.com', 'temp-pass', 'acme')).toBe(true)
    expect(auth.mustChangePassword).toBe(true)
    // No refresh token in the reply: nothing stale is written.
    expect(localStorage.getItem('bodhiorchard_refresh_token')).toBeNull()
  })

  it('signs in but says so when the profile does not load', async () => {
    post.mockResolvedValue({ data: { access_token: 'a1' } })
    get.mockRejectedValue(httpError(500))
    const auth = useAuthStore()
    expect(await auth.login('ana@example.com', 'secret-pass', 'acme')).toBe(true)
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.user).toBeNull()
    expect(auth.loginError).toBe('Logged in but failed to load profile. Please refresh.')
  })

  it('shows a plain message for wrong credentials and keeps no token', async () => {
    post.mockRejectedValue(httpError(401, 'Invalid credentials'))
    const auth = useAuthStore()
    expect(await auth.login('ana@example.com', 'wrong', 'acme')).toBe(false)
    expect(auth.loginError).toBe('Invalid email or password.')
    expect(auth.isAuthenticated).toBe(false)
    expect(localStorage.getItem('bodhiorchard_token')).toBeNull()
  })

  it('turns a validation error into sentences, not raw JSON', async () => {
    post.mockRejectedValue(httpError(422, [
      { loc: ['body', 'email'], msg: 'value is not a valid email address' },
    ]))
    const auth = useAuthStore()
    expect(await auth.login('not-an-email', 'x', 'acme')).toBe(false)
    expect(auth.loginError).toBe('value is not a valid email address')
  })

  it('reports an unreachable server as a network problem', async () => {
    post.mockRejectedValue(new Error('Network Error'))
    const auth = useAuthStore()
    expect(await auth.login('ana@example.com', 'secret-pass', 'acme')).toBe(false)
    expect(auth.loginError).toBe('Network error. Please check your connection.')
  })

  it('clears the previous failure on the next attempt', async () => {
    post.mockRejectedValueOnce(httpError(401))
    post.mockResolvedValueOnce({ data: { access_token: 'a1' } })
    const auth = useAuthStore()
    await auth.login('ana@example.com', 'wrong', 'acme')
    await auth.login('ana@example.com', 'right-pass', 'acme')
    expect(auth.loginError).toBeNull()
  })
})

describe('logout', () => {
  it('forgets the tokens, the user, the last error and the remembered page', async () => {
    post.mockResolvedValue({ data: { access_token: 'a1', refresh_token: 'r1' } })
    const auth = useAuthStore()
    await auth.login('ana@example.com', 'secret-pass', 'acme')
    auth.loginError = 'stale'
    rememberReturnTo('/people/u2')
    expect(sessionStorage.length).toBe(1)

    auth.logout()

    expect(auth.isAuthenticated).toBe(false)
    expect(auth.user).toBeNull()
    expect(auth.loginError).toBeNull()
    expect(localStorage.getItem('bodhiorchard_token')).toBeNull()
    expect(localStorage.getItem('bodhiorchard_refresh_token')).toBeNull()
    expect(takeReturnTo()).toBeNull()
  })
})

describe('token kept in step with the axios refresh', () => {
  it('starts from the stored token and follows a refresh event', () => {
    localStorage.setItem('bodhiorchard_token', 'old')
    const auth = useAuthStore()
    expect(auth.token).toBe('old')
    window.dispatchEvent(new CustomEvent('glideship:token-refreshed', { detail: { accessToken: 'new' } }))
    expect(auth.token).toBe('new')
  })

  it('ignores a refresh event without a token', () => {
    localStorage.setItem('bodhiorchard_token', 'old')
    const auth = useAuthStore()
    window.dispatchEvent(new CustomEvent('glideship:token-refreshed', { detail: {} }))
    expect(auth.token).toBe('old')
  })
})

describe('fetchUser', () => {
  it('does not call the API when signed out', async () => {
    await useAuthStore().fetchUser()
    expect(get).not.toHaveBeenCalled()
  })
})

describe('changePassword', () => {
  it('clears the must-change flag on success', async () => {
    post.mockResolvedValueOnce({ data: { access_token: 'a1', must_change_password: true } })
    const auth = useAuthStore()
    await auth.login('ana@example.com', 'temp-pass', 'acme')
    post.mockResolvedValueOnce({ data: {} })
    expect(await auth.changePassword('a-new-long-pass')).toBeNull()
    expect(post).toHaveBeenLastCalledWith('/v1/auth/change-password', { new_password: 'a-new-long-pass' })
    expect(auth.mustChangePassword).toBe(false)
  })

  it('asks to sign in again when the session has expired', async () => {
    post.mockRejectedValue(httpError(401))
    expect(await useAuthStore().changePassword('a-new-long-pass')).toBe('Session expired. Please log in again.')
  })

  it("shows the server's reason otherwise, keeping the flag", async () => {
    post.mockResolvedValueOnce({ data: { access_token: 'a1', must_change_password: true } })
    const auth = useAuthStore()
    await auth.login('ana@example.com', 'temp-pass', 'acme')
    post.mockRejectedValueOnce(httpError(400, 'Password reused'))
    expect(await auth.changePassword('temp-pass')).toBe('Password reused')
    expect(auth.mustChangePassword).toBe(true)
  })
})
