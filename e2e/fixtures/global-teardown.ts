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
 * Fails the run if the dev server re-optimised its dependencies mid-run.
 * Vite then fully reloads every open page, which wipes forms and drops
 * websockets in front of a user. The stack starts Vite on a cold cache
 * (`--force`), so a dependency the startup pass misses always shows here.
 */
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { STACK_DIR } from '../stack/config.ts'

const RELOAD = /optimized dependencies changed\. reloading/

export default function globalTeardown(): void {
  let log: string
  try {
    log = readFileSync(path.join(STACK_DIR, 'logs', 'frontend.log'), 'utf8')
  } catch {
    return // A stack this run didn't start, from another tool: nothing to check.
  }
  const reloads = log.split('\n').filter((line) => RELOAD.test(line))
  if (reloads.length > 0) {
    const found = log.split('\n').filter((line) => line.includes('new dependencies optimized'))
    throw new Error(
      `Vite reloaded the app ${reloads.length} time(s) mid-run. ` +
        `Add these to optimizeDeps in frontend/vite.config.ts:\n${found.join('\n')}`,
    )
  }
}
