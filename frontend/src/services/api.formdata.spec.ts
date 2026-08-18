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
 * Multipart contract for the shared axios instance.
 *
 * The instance defaults to ``Content-Type: application/json``, and axios's
 * own ``transformRequest`` branches on that header: given a FormData body
 * with a JSON content-type it returns ``JSON.stringify(formDataToJSON(data))``
 * instead of the form. Every File is lost, and FastAPI answers
 * ``{"type": "missing", "loc": ["body", "file"]}``.
 *
 * These tests drive axios's REAL transformRequest rather than asserting on
 * our own header bookkeeping — that's the function whose behaviour the bug
 * hinged on, so it's the one worth pinning.
 *
 * ``.spec.ts`` (not ``.test.ts``) because vitest.config.ts maps that suffix
 * to jsdom, and these need ``localStorage`` / ``File`` / ``FormData``.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import axios, { AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import api, { applyRequestHeaders } from './api'

type TransformFn = (
  this: unknown,
  data: unknown,
  headers: AxiosHeaders,
) => unknown

const transformRequest = ([] as TransformFn[]).concat(
  axios.defaults.transformRequest as unknown as TransformFn[],
)[0]

function configWith(data: unknown): InternalAxiosRequestConfig {
  return {
    data,
    headers: new AxiosHeaders({ 'Content-Type': 'application/json' }),
  } as InternalAxiosRequestConfig
}

/** What axios would actually put on the wire for this config. */
function bodyOnTheWire(config: InternalAxiosRequestConfig): unknown {
  return transformRequest.call({}, config.data, config.headers as AxiosHeaders)
}

describe('shared axios instance — FormData handling', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('keeps a FormData body intact instead of rewriting it to JSON', () => {
    const form = new FormData()
    form.append('file', new File(['<html></html>'], 'wireframe.html', { type: 'text/html' }))

    const config = applyRequestHeaders(configWith(form))

    // The regression: without the interceptor this came back as the string
    // '{"file":{}}' and the upload 422'd on a missing file field.
    expect(bodyOnTheWire(config)).toBe(form)
    expect(typeof bodyOnTheWire(config)).not.toBe('string')
  })

  it('clears the JSON content-type so the browser can set the boundary', () => {
    const form = new FormData()
    form.append('file', new File(['x'], 'a.html'))

    const config = applyRequestHeaders(configWith(form))

    // Only the browser can generate the multipart boundary; any value we
    // leave here (including a hand-written 'multipart/form-data') produces
    // a body the server cannot parse.
    expect((config.headers as AxiosHeaders).getContentType()).toBeFalsy()
  })

  it('leaves JSON requests on application/json', () => {
    const config = applyRequestHeaders(configWith({ status: 'design' }))

    expect((config.headers as AxiosHeaders).getContentType()).toBe('application/json')
    expect(bodyOnTheWire(config)).toBe('{"status":"design"}')
  })

  it('still attaches the bearer token', () => {
    localStorage.setItem('bodhiorchard_token', 'tok-123')
    const form = new FormData()
    form.append('file', new File(['x'], 'a.html'))

    const config = applyRequestHeaders(configWith(form))

    expect(config.headers.Authorization).toBe('Bearer tok-123')
  })

  it('is actually registered on the shared instance', async () => {
    // Without this, deleting the `interceptors.request.use` line leaves
    // every test above green while the production bug returns in full.
    const form = new FormData()
    form.append('file', new File(['x'], 'a.html'))
    let seen: InternalAxiosRequestConfig | null = null

    const adapterId = api.interceptors.request.use((c) => c)
    const original = api.defaults.adapter
    api.defaults.adapter = async (config) => {
      seen = config as InternalAxiosRequestConfig
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
    }
    try {
      await api.post('/v1/test', form)
    } finally {
      api.defaults.adapter = original
      api.interceptors.request.eject(adapterId)
    }

    // The body reaching the adapter is still the form. Without the
    // interceptor registered, transformRequest would have replaced it with
    // the string '{"file":{}}' before the adapter ever saw it.
    expect((seen as unknown as InternalAxiosRequestConfig).data).toBe(form)
    const handlers = api.interceptors.request.handlers ?? []
    expect(handlers.some((h) => h?.fulfilled === applyRequestHeaders)).toBe(true)
  })
})
