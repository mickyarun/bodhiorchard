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
 * When the shared axios instance gives up on the session: no refresh
 * token or a refused refresh signs out once and remembers the page (but
 * never from login or setup); a 403 asking for a password change sends
 * the browser there with the session kept. ``.spec.ts`` for jsdom.
 */
import axios from 'axios'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import api from './api'
import {
  REFRESH, TOKEN, acceptOnly, navigationCount, recordNavigations, resetSession, respondWith,
  restoreAdapter, stopRecordingNavigations,
} from './__tests__/apiSession'
import { forgetReturnTo, takeReturnTo } from '@/utils/returnTo'

let refreshPost: MockInstance<typeof axios.post>

beforeAll(recordNavigations)
afterAll(stopRecordingNavigations)

beforeEach(() => {
  resetSession('/buds/42')
  forgetReturnTo()
  refreshPost = vi.spyOn(axios, 'post')
})

afterEach(() => {
  restoreAdapter()
  vi.restoreAllMocks()
})

describe('a 401 without a refresh token', () => {
  beforeEach(() => {
    localStorage.setItem(TOKEN, 'expired')
    acceptOnly('fresh')
  })

  it('signs out, remembers the page and goes to login', async () => {
    await expect(api.get('/v1/buds')).rejects.toMatchObject({ response: { status: 401 } })
    expect(refreshPost).not.toHaveBeenCalled()
    expect(localStorage.getItem(TOKEN)).toBeNull()
    expect(takeReturnTo()).toBe('/buds/42')
    expect(navigationCount()).toBe(1)
  })

  it.each(['/login', '/setup'])('clears the session but stays on %s', async (path) => {
    window.history.replaceState(null, '', path)
    await expect(api.get('/v1/auth/me')).rejects.toMatchObject({ response: { status: 401 } })
    expect(localStorage.getItem(TOKEN)).toBeNull()
    expect(takeReturnTo()).toBeNull()
    expect(navigationCount()).toBe(0)
  })
})

describe('a refused refresh', () => {
  beforeEach(() => {
    localStorage.setItem(TOKEN, 'expired')
    localStorage.setItem(REFRESH, 'refresh-1')
    acceptOnly('fresh')
  })

  it('signs out and remembers the page', async () => {
    refreshPost.mockRejectedValue(new Error('refresh token expired'))
    await expect(api.get('/v1/buds')).rejects.toThrow('refresh token expired')
    expect(localStorage.getItem(TOKEN)).toBeNull()
    expect(localStorage.getItem(REFRESH)).toBeNull()
    expect(takeReturnTo()).toBe('/buds/42')
    expect(navigationCount()).toBe(1)
  })

  it('fails every waiting request and redirects once', async () => {
    let refuse: (err: unknown) => void = () => undefined
    refreshPost.mockReturnValue(new Promise((_, reject) => { refuse = reject }))

    const first = api.get('/v1/buds')
    const second = api.get('/v1/bugs')
    const outcomes = Promise.allSettled([first, second])
    await vi.waitFor(() => expect(refreshPost).toHaveBeenCalledOnce())
    refuse(new Error('refresh token expired'))

    const [a, b] = await outcomes
    expect(a.status).toBe('rejected')
    expect(b.status).toBe('rejected')
    expect(refreshPost).toHaveBeenCalledOnce()
    expect(navigationCount()).toBe(1)
  })
})

describe('a 403', () => {
  it('asking for a password change goes there, keeping the session and no return page', async () => {
    localStorage.setItem(TOKEN, 'ok')
    respondWith(403, { detail: 'Password change required' })
    await expect(api.get('/v1/buds')).rejects.toMatchObject({ response: { status: 403 } })
    expect(navigationCount()).toBe(1)
    // Unlike a sign-out, nothing is remembered for after login.
    expect(takeReturnTo()).toBeNull()
    expect(localStorage.getItem(TOKEN)).toBe('ok')
  })

  it('asking for a password change stays put on the change-password page', async () => {
    window.history.replaceState(null, '', '/change-password')
    respondWith(403, { detail: 'Password change required' })
    await expect(api.post('/v1/auth/change-password', {})).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(navigationCount()).toBe(0)
  })

  it('for anything else is left to the caller', async () => {
    respondWith(403, { detail: 'Insufficient permissions.' })
    await expect(api.get('/v1/buds')).rejects.toMatchObject({
      response: { status: 403, data: { detail: 'Insufficient permissions.' } },
    })
    expect(navigationCount()).toBe(0)
    expect(refreshPost).not.toHaveBeenCalled()
  })
})
