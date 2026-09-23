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
 * Error-body contract for ``responseType: 'blob'`` requests.
 *
 * A blob request gets a Blob back even when the server fails, so
 * ``error.response.data`` holds an unparsed Blob instead of the
 * backend's ``{"detail": "..."}``. Everything downstream reads
 * ``.detail`` — ``extractApiError``, the attachment tile's error text,
 * the change-password redirect — and silently degrades to axios's
 * generic "Request failed with status code N".
 *
 * The response interceptor parses the Blob back into the normal shape
 * so no blob caller needs special handling. These tests drive the REAL
 * instance through a stub adapter, so they pin the interceptor's actual
 * behaviour rather than a reimplementation of it.
 *
 * ``.spec.ts`` (not ``.test.ts``) because vitest.config.ts maps that
 * suffix to jsdom, and these need ``Blob`` and ``localStorage``.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import type { AxiosError, AxiosRequestConfig } from 'axios'
import api from './api'
import { extractApiError } from '@/utils/errors'

const realAdapter = api.defaults.adapter

// jsdom implements Blob but not `Blob.prototype.text()`, which every
// target browser has had for years (Chrome 76, Firefox 69, Safari 14).
// Polyfill via FileReader — which jsdom does implement — so these tests
// exercise the interceptor's real code path instead of silently taking
// its parse-failure branch and passing for the wrong reason.
if (typeof Blob.prototype.text !== 'function') {
  Blob.prototype.text = function text(this: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = () => reject(reader.error)
      reader.readAsText(this)
    })
  }
}

/** Make the instance fail every request with this status and body. */
function respondWith(status: number, body: string, contentType = 'application/json'): void {
  api.defaults.adapter = async (config: AxiosRequestConfig) => {
    const response = {
      data: new Blob([body], { type: contentType }),
      status,
      statusText: 'Error',
      headers: {},
      config,
    }
    // Mirror axios's own rejection shape for a non-2xx status.
    return Promise.reject(
      Object.assign(new Error(`Request failed with status code ${status}`), {
        isAxiosError: true,
        response,
        config,
      }),
    )
  }
}

async function failedBlobRequest(): Promise<AxiosError> {
  try {
    await api.get('/v1/bugs/x/attachments/y', { responseType: 'blob' })
    throw new Error('request unexpectedly succeeded')
  } catch (err) {
    return err as AxiosError
  }
}

beforeEach(() => {
  localStorage.setItem('bodhiorchard_token', 'test-token')
})

afterEach(() => {
  api.defaults.adapter = realAdapter
  localStorage.removeItem('bodhiorchard_token')
})

describe('shared axios instance — blob error bodies', () => {
  it('parses a JSON error body so callers can read detail', async () => {
    respondWith(404, JSON.stringify({ detail: 'Attachment not found' }))
    const err = await failedBlobRequest()

    expect(err.response?.data).toEqual({ detail: 'Attachment not found' })
    expect(err.response?.data).not.toBeInstanceOf(Blob)
  })

  it('lets extractApiError surface the backend reason', async () => {
    // This is the user-visible payoff: the attachment tile renders this
    // string, and before the fix it always read "Request failed with
    // status code 404" no matter what the route said.
    respondWith(404, JSON.stringify({ detail: 'Attachment not found' }))
    const err = await failedBlobRequest()

    expect(extractApiError(err, 'fallback')).toBe('Attachment not found')
  })

  it('leaves a non-JSON body alone rather than throwing', async () => {
    // An nginx 413/502 page is HTML, not JSON. Parsing must fail softly
    // — a throw inside the interceptor would replace the real HTTP
    // error with a JSON.parse SyntaxError.
    respondWith(413, '<html><body>413 Request Entity Too Large</body></html>', 'text/html')
    const err = await failedBlobRequest()

    expect(err.response?.data).toBeInstanceOf(Blob)
    expect(err.response?.status).toBe(413)
  })

  it('keeps working when the body is empty', async () => {
    respondWith(502, '')
    const err = await failedBlobRequest()

    expect(err.response?.status).toBe(502)
    expect(err.response?.data).toBeInstanceOf(Blob)
  })
})
