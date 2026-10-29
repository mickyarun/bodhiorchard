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

/** Poll until a stack service answers, with one deadline per service. */
import { setTimeout as sleep } from 'node:timers/promises'

const POLL_MS = 500

export async function waitFor(
  what: string,
  ready: () => Promise<boolean>,
  timeoutMs = 120_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMs
  let lastError: unknown
  while (Date.now() < deadline) {
    try {
      if (await ready()) return
    } catch (error) {
      lastError = error
    }
    await sleep(POLL_MS)
  }
  const detail = lastError instanceof Error ? `: ${lastError.message}` : ''
  throw new Error(`${what} was not ready after ${timeoutMs / 1000}s${detail}`)
}

/** Resolves once `url` answers with a status below 500. */
export function waitForHttp(what: string, url: string, timeoutMs?: number): Promise<void> {
  return waitFor(
    what,
    async () => (await fetch(url, { signal: AbortSignal.timeout(5_000) })).status < 500,
    timeoutMs,
  )
}
