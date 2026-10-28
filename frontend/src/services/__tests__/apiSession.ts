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
 * Test support for the shared axios instance's session handling: a stub
 * adapter that accepts one bearer token, and a record of the page
 * navigations jsdom refused (it can't navigate, and says so on its
 * virtual console). Used by the ``api.*.spec.ts`` files only.
 */
import type { AxiosRequestConfig, AxiosResponse } from 'axios'
import api from '@/services/api'

type JsdomErrorListener = (err: Error) => void

// Vitest's jsdom environment exposes the JSDOM instance as a global.
declare const jsdom: {
  virtualConsole: {
    on(event: 'jsdomError', listener: JsdomErrorListener): void
    off(event: 'jsdomError', listener: JsdomErrorListener): void
    listeners(event: 'jsdomError'): JsdomErrorListener[]
  }
}

export const TOKEN = 'bodhiorchard_token'
export const REFRESH = 'bodhiorchard_refresh_token'

/** Resolve with ``data``, or reject the way axios does for an error status. */
export function reply(config: AxiosRequestConfig, status: number, data: unknown): Promise<AxiosResponse> {
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

/** Authorization header of every request the stub adapter saw, in order. */
export const seen: string[] = []

/** Accept only ``Bearer <goodToken>``; anything else gets a 401. */
export function acceptOnly(goodToken: string): void {
  api.defaults.adapter = async (config: AxiosRequestConfig) => {
    const auth = String(config.headers?.Authorization ?? '')
    seen.push(auth)
    return auth === `Bearer ${goodToken}`
      ? reply(config, 200, { url: config.url })
      : reply(config, 401, { detail: 'Not authenticated' })
  }
}

/** Answer every request with this status and body. */
export function respondWith(status: number, data: unknown): void {
  api.defaults.adapter = async (config: AxiosRequestConfig) => reply(config, status, data)
}

const realAdapter = api.defaults.adapter
const navigations: string[] = []
const record: JsdomErrorListener = (err) => {
  if (err.message.includes('navigation')) navigations.push(err.message)
}
let silenced: JsdomErrorListener[] = []

/**
 * Count jsdom's refused navigations instead of printing them. Call in
 * ``beforeAll``; ``stopRecordingNavigations`` puts the printing back.
 */
export function recordNavigations(): void {
  silenced = jsdom.virtualConsole.listeners('jsdomError')
  for (const listener of silenced) jsdom.virtualConsole.off('jsdomError', listener)
  jsdom.virtualConsole.on('jsdomError', record)
}

export function stopRecordingNavigations(): void {
  jsdom.virtualConsole.off('jsdomError', record)
  for (const listener of silenced) jsdom.virtualConsole.on('jsdomError', listener)
  silenced = []
}

/** How many times the page tried to navigate since the last reset. */
export function navigationCount(): number {
  return navigations.length
}

/** Fresh state for each test: signed out, on ``path``, no stub replies seen. */
export function resetSession(path: string): void {
  seen.length = 0
  navigations.length = 0
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState(null, '', path)
}

export function restoreAdapter(): void {
  api.defaults.adapter = realAdapter
}
