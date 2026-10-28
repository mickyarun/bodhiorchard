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
 * The shared axios instance's session handling: the bearer token goes on
 * every request, a 401 trades the refresh token for a new pair once and
 * retries, concurrent 401s share that one refresh, and a refresh that
 * fails signs the browser out. Requests run through a stub adapter that
 * accepts only one token; the refresh call itself is the bare
 * ``axios.post`` and is spied. ``.spec.ts`` for jsdom.
 */
import axios, { type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi, type MockInstance } from 'vitest'
import api from './api'
import { forgetReturnTo, takeReturnTo } from '@/utils/returnTo'

const realAdapter = api.defaults.adapter
const TOKEN = 'bodhiorchard_token'
const REFRESH = 'bodhiorchard_refresh_token'

function reply(config: AxiosRequestConfig, status: number, data: unknown): Promise<AxiosResponse> {
  const response = { data, status, statusText: '', headers: {}, config } as AxiosResponse
  if (status < 400) return Promise.resolve(response)
  return Promise.reject(
    Object.assign(new Error(`Request failed with status code ${status}`), {
      isAxiosError: true,
      config,
      response,
    }),
  )
}

/** Authorization header of every request the adapter saw, in order. */
let seen: string[] = []

function acceptOnly(goodToken: string): void {
  api.defaults.adapter = async (config: AxiosRequestConfig) => {
    const auth = String(config.headers?.Authorization ?? '')
    seen.push(auth)
    return auth === `Bearer ${goodToken}`
      ? reply(config, 200, { url: config.url })
      : reply(config, 401, { detail: 'Not authenticated' })
  }
}

// Vitest's jsdom environment exposes the JSDOM instance as a global.
declare const jsdom: {
  virtualConsole: {
    on(event: 'jsdomError', listener: (err: Error) => void): void
    off(event: 'jsdomError', listener: (err: Error) => void): void
  }
}

let refreshPost: MockInstance<typeof axios.post>
/** jsdom can't navigate; it reports each attempt on its virtual console. */
let jsdomErrors: string[] = []
const recordJsdomError = (err: Error): void => { jsdomErrors.push(err.message) }

function navigationAttempted(): boolean {
  return jsdomErrors.some(message => message.includes('navigation'))
}

beforeEach(() => {
  seen = []
  localStorage.clear()
  sessionStorage.clear()
  forgetReturnTo()
  window.history.replaceState(null, '', '/buds/42')
  jsdomErrors = []
  jsdom.virtualConsole.on('jsdomError', recordJsdomError)
  refreshPost = vi.spyOn(axios, 'post')
})

afterEach(() => {
  jsdom.virtualConsole.off('jsdomError', recordJsdomError)
  api.defaults.adapter = realAdapter
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

  it('signs out and remembers the page when the refresh is refused', async () => {
    refreshPost.mockRejectedValue(new Error('refresh token expired'))
    await expect(api.get('/v1/buds')).rejects.toThrow('refresh token expired')
    expect(localStorage.getItem(TOKEN)).toBeNull()
    expect(localStorage.getItem(REFRESH)).toBeNull()
    expect(takeReturnTo()).toBe('/buds/42')
    expect(navigationAttempted()).toBe(true)
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
  })
})

describe('a 401 without a refresh token', () => {
  it('signs out straight away', async () => {
    localStorage.setItem(TOKEN, 'expired')
    acceptOnly('fresh')
    await expect(api.get('/v1/buds')).rejects.toMatchObject({ response: { status: 401 } })
    expect(refreshPost).not.toHaveBeenCalled()
    expect(localStorage.getItem(TOKEN)).toBeNull()
    expect(takeReturnTo()).toBe('/buds/42')
  })
})

describe('a 403', () => {
  function respond403(detail: string): void {
    api.defaults.adapter = async (config: AxiosRequestConfig) => reply(config, 403, { detail })
  }

  it('asking for a password change sends the browser there and keeps the session', async () => {
    localStorage.setItem(TOKEN, 'ok')
    respond403('Password change required')
    await expect(api.get('/v1/buds')).rejects.toMatchObject({ response: { status: 403 } })
    expect(navigationAttempted()).toBe(true)
    expect(localStorage.getItem(TOKEN)).toBe('ok')
  })

  it('asking for a password change stays put on the change-password page', async () => {
    window.history.replaceState(null, '', '/change-password')
    respond403('Password change required')
    await expect(api.post('/v1/auth/change-password', {})).rejects.toMatchObject({
      response: { status: 403 },
    })
    expect(navigationAttempted()).toBe(false)
  })

  it('for anything else is left to the caller', async () => {
    respond403('Insufficient permissions.')
    await expect(api.get('/v1/buds')).rejects.toMatchObject({
      response: { status: 403, data: { detail: 'Insufficient permissions.' } },
    })
    expect(navigationAttempted()).toBe(false)
    expect(refreshPost).not.toHaveBeenCalled()
  })
})
