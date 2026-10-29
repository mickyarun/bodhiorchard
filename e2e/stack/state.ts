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
 * Ownership of this checkout's stack. The runner writes its pid and each
 * child's process group to STATE_FILE. A second start refuses while the
 * owner lives (rather than wiping a running stack), and a start after a run
 * that was killed outright stops the children it left behind.
 */
import { execFileSync } from 'node:child_process'
import { readFileSync, rmSync, writeFileSync } from 'node:fs'
import { STATE_FILE } from './config.ts'

interface Group {
  pid: number
  /** Part of the command line, to confirm the pid wasn't reused since. */
  marker: string
}

interface StackState {
  ownerPid: number
  groups: Group[]
}

function read(): StackState | undefined {
  try {
    return JSON.parse(readFileSync(STATE_FILE, 'utf8')) as StackState
  } catch {
    return undefined
  }
}

function write(state: StackState): void {
  writeFileSync(STATE_FILE, JSON.stringify(state))
}

function alive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch (error) {
    return (error as NodeJS.ErrnoException).code === 'EPERM'
  }
}

function commandOf(pid: number): string {
  try {
    return execFileSync('ps', ['-ww', '-o', 'command=', '-p', String(pid)], { encoding: 'utf8' })
  } catch {
    return ''
  }
}

/** Takes the stack for this process; throws if another runner owns it. */
export function claimStack(): void {
  const previous = read()
  if (previous && previous.ownerPid !== process.pid && alive(previous.ownerPid)) {
    throw new Error(
      `this checkout's stack is already running (pid ${previous.ownerPid}). ` +
        `Reuse it, or stop it first. If that pid is not a stack, delete ${STATE_FILE}.`,
    )
  }
  for (const group of previous?.groups ?? []) {
    if (commandOf(group.pid).includes(group.marker)) {
      try {
        process.kill(-group.pid, 'SIGKILL')
      } catch {
        // Gone in the meantime.
      }
    }
  }
  write({ ownerPid: process.pid, groups: [] })
}

export function recordGroup(pid: number, marker: string): void {
  const state = read() ?? { ownerPid: process.pid, groups: [] }
  state.groups.push({ pid, marker })
  write(state)
}

export function releaseStack(): void {
  if (read()?.ownerPid === process.pid) rmSync(STATE_FILE, { force: true })
}
