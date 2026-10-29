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
 * End-of-run checks, on each backend and frontend of the stack:
 *
 * - nothing the fakes refused during this run, including what a test's
 *   background work caused after its own check ran, and what job workers
 *   or scheduler loops did outside any test;
 * - the dev server never re-optimised its dependencies mid-run. Vite then
 *   fully reloads every open page, which wipes forms and drops websockets
 *   in front of a user. The stack starts Vite on a cold cache (`--force`),
 *   so a dependency the startup pass misses always shows here.
 */
import { readFileSync } from 'node:fs'
import { request } from '@playwright/test'
import { STACKS, type StackTarget } from '../stack/config.ts'
import { startPoint, viteLogPath } from './run.ts'
import type { GuardReport } from './types.ts'

const RELOAD = /optimized dependencies changed\. reloading/

function viteReloads(target: StackTarget): string[] {
  let log: string
  try {
    // Only this run's part of the log: a reused stack keeps appending to it.
    log = readFileSync(viteLogPath(target)).subarray(startPoint(target).viteLogBytes).toString('utf8')
  } catch {
    return [] // A stack this run didn't start, from another tool: nothing to check.
  }
  if (!log.split('\n').some((line) => RELOAD.test(line))) return []
  const missed = log.split('\n').filter((line) => line.includes('new dependencies optimized'))
  return [`Vite (${target.name}) reloaded the app mid-run. Pre-bundle these in frontend/vite.config.ts:`, ...missed]
}

async function refusals(target: StackTarget): Promise<string[]> {
  const api = await request.newContext({ baseURL: target.backendUrl })
  try {
    const since = startPoint(target)
    const response = await api.get('/__e2e/guard', {
      params: { all: 'true', sinceViolations: since.violations, sinceAgentProblems: since.agentProblems },
    })
    if (!response.ok()) return [`could not read the ${target.name} guard report (${response.status()})`]
    const report = (await response.json()) as GuardReport
    return [...report.violations, ...report.agentProblems].map((line) => `${target.name}: ${line}`)
  } finally {
    await api.dispose()
  }
}

export default async function globalTeardown(): Promise<void> {
  const problems = [
    ...STACKS.flatMap(viteReloads),
    ...(await Promise.all(STACKS.map(refusals))).flat(),
  ]
  if (problems.length > 0) throw new Error(`The run left problems behind:\n${problems.join('\n')}`)
}
