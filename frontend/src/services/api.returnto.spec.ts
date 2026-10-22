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
 * A session that runs out mid-use sends the browser to login; the page it
 * was on (fragment included) is remembered for after signing in again.
 * Drives the real instance through a stub adapter. ``.spec.ts`` for jsdom.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AxiosRequestConfig } from 'axios'
import api from './api'
import { takeReturnTo } from '@/utils/returnTo'

const realAdapter = api.defaults.adapter

function unauthorized(): void {
  api.defaults.adapter = async (config: AxiosRequestConfig) =>
    Promise.reject(
      Object.assign(new Error('Request failed with status code 401'), {
        isAxiosError: true,
        config,
        response: { data: { detail: 'Not authenticated' }, status: 401, statusText: '', headers: {}, config },
      }),
    )
}

describe('session ran out', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    localStorage.setItem('bodhiorchard_token', 'expired') // and no refresh token
    // jsdom can't navigate; the redirect itself isn't what's under test.
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    unauthorized()
  })

  afterEach(() => {
    api.defaults.adapter = realAdapter
    vi.restoreAllMocks()
  })

  it('remembers the page it was on, fragment included', async () => {
    window.history.replaceState(null, '', '/leave?tab=mine#slackCode=c&slackState=s')
    await expect(api.post('/v1/leave/slack-status/me/finish')).rejects.toBeTruthy()
    expect(takeReturnTo()).toBe('/leave?tab=mine#slackCode=c&slackState=s')
    expect(localStorage.getItem('bodhiorchard_token')).toBeNull()
  })

  it('remembers nothing from the login page itself', async () => {
    window.history.replaceState(null, '', '/login')
    await expect(api.get('/v1/auth/me')).rejects.toBeTruthy()
    expect(takeReturnTo()).toBeNull()
  })
})
