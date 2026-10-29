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
 * What identifies this Playwright run on a stack that may outlive it
 * (`npm run stack` keeps one up across runs). Global setup records a run id
 * and, per stack, where its guard logs and Vite log stood. It puts them in
 * `process.env`, which workers inherit and teardown (same process) reads,
 * so a run only ever answers for what happened during it.
 */
import { randomBytes } from 'node:crypto'
import { statSync } from 'node:fs'
import path from 'node:path'
import { STACK_DIR, type StackTarget } from '../stack/config.ts'

const RUN_ID = 'E2E_RUN_ID'

export interface StartPoint {
  violations: number
  agentProblems: number
  viteLogBytes: number
}

export function startRun(): void {
  process.env[RUN_ID] = randomBytes(4).toString('hex')
}

/** Set by global setup; a fixed value outside a full run (a lone `--list`, say). */
export function runId(): string {
  return process.env[RUN_ID] ?? 'no-run'
}

export function viteLogPath(target: StackTarget): string {
  return path.join(STACK_DIR, 'logs', `frontend-${target.name}.log`)
}

export function viteLogBytes(target: StackTarget): number {
  try {
    return statSync(viteLogPath(target)).size
  } catch {
    return 0
  }
}

const key = (target: StackTarget): string => `E2E_START_${target.name.toUpperCase()}`

export function saveStartPoint(target: StackTarget, point: StartPoint): void {
  process.env[key(target)] = JSON.stringify(point)
}

export function startPoint(target: StackTarget): StartPoint {
  const raw = process.env[key(target)]
  return raw ? (JSON.parse(raw) as StartPoint) : { violations: 0, agentProblems: 0, viteLogBytes: 0 }
}
