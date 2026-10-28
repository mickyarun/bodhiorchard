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
 * The shared axios instance's token handling: the bearer token goes on
 * every request, and a 401 trades the refresh token for a new pair once
 * and retries, with concurrent 401s sharing that one refresh. The refresh
 * call itself is the bare ``axios.post`` and is spied. ``.spec.ts`` for
 * jsdom.
 */
import axios from 'axios'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import api from './api'
import {
  REFRESH, TOKEN, acceptOnly, navigationCount, recordNavigations, resetSession, restoreAdapter, seen,
  stopRecordingNavigations,
} from './__tests__/apiSession'
import { forgetReturnTo } from '@/utils/returnTo'

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

describe('request header', () => {
  it('sends the stored token as a bearer token', async () => {
    localStorage.setItem(TOKEN, 'fresh')
    acceptOnly('fresh')
    await api.get('/v1/buds')
    expect(seen).toEqual(['Bearer fresh'])
  })

  it('sends no Authorization header when signed out', async () => {
    window.history.replaceState(null, '', '/login')
    acceptOnly('fresh')
    await expect(api.get('/v1/buds')).rejects.toMatchObject({ response: { status: 401 } })
    expect(seen).toEqual([''])
  })
})

describe('a 401 with a refresh token', () => {
  beforeEach(() => {
    localStorage.setItem(TOKEN, 'expired')
    localStorage.setItem(REFRESH, 'refresh-1')
    acceptOnly('fresh')
  })

  it('refreshes once, stores the new pair, and retries with the new token', async () => {
    refreshPost.mockResolvedValue({ data: { access_token: 'fresh', refresh_token: 'refresh-2' } })
    const announced = vi.fn()
    window.addEventListener('glideship:token-refreshed', announced)

    const { data } = await api.get('/v1/buds')

    window.removeEventListener('glideship:token-refreshed', announced)
    expect(data).toEqual({ url: '/v1/buds' })
    expect(refreshPost).toHaveBeenCalledOnce()
    expect(refreshPost.mock.calls[0][0]).toMatch(/\/v1\/auth\/refresh$/)
    expect(refreshPost.mock.calls[0][1]).toEqual({ refresh_token: 'refresh-1' })
    expect(seen).toEqual(['Bearer expired', 'Bearer fresh'])
    expect(localStorage.getItem(TOKEN)).toBe('fresh')
    expect(localStorage.getItem(REFRESH)).toBe('refresh-2')
    expect((announced.mock.calls[0][0] as CustomEvent).detail).toEqual({ accessToken: 'fresh' })
    expect(navigationCount()).toBe(0)
  })

  it('shares one refresh between requests that fail together', async () => {
    let finish: (value: unknown) => void = () => undefined
    refreshPost.mockReturnValue(new Promise(resolve => { finish = resolve }))

    const first = api.get('/v1/buds')
    const second = api.get('/v1/bugs')
    await vi.waitFor(() => expect(seen).toHaveLength(2))
    finish({ data: { access_token: 'fresh', refresh_token: 'refresh-2' } })

    const [a, b] = await Promise.all([first, second])
    expect(a.data).toEqual({ url: '/v1/buds' })
    expect(b.data).toEqual({ url: '/v1/bugs' })
    expect(refreshPost).toHaveBeenCalledOnce()
  })

  it('does not refresh again when the retried request is still refused', async () => {
    // The server hands back a token it then rejects: one refresh, no loop.
    refreshPost.mockResolvedValue({ data: { access_token: 'still-bad', refresh_token: 'r' } })
    await expect(api.get('/v1/buds')).rejects.toMatchObject({ response: { status: 401 } })
    expect(refreshPost).toHaveBeenCalledOnce()
    expect(seen).toEqual(['Bearer expired', 'Bearer still-bad'])
  })

  it.each(['/v1/auth/login', '/v1/auth/refresh'])('never refreshes for %s', async (url) => {
    await expect(api.post(url, {})).rejects.toMatchObject({ response: { status: 401 } })
    expect(refreshPost).not.toHaveBeenCalled()
    expect(localStorage.getItem(TOKEN)).toBe('expired')
    expect(navigationCount()).toBe(0)
  })
})
