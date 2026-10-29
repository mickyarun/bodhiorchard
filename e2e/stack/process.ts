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
 * Child processes of the stack (migrations, backend, multiplayer, Vite).
 * Each runs in its own process group so stopping it also stops whatever it
 * spawned (Vite's esbuild, for one), and writes to `.stack/logs/<name>.log`.
 */
import { spawn, type ChildProcess } from 'node:child_process'
import { createWriteStream, readFileSync } from 'node:fs'
import path from 'node:path'
import { STACK_DIR } from './config.ts'

export interface Service {
  name: string
  child: ChildProcess
  logPath: string
}

export interface ServiceOptions {
  cwd: string
  env: NodeJS.ProcessEnv
}

export function startService(name: string, command: string, args: string[], opts: ServiceOptions): Service {
  const logPath = path.join(STACK_DIR, 'logs', `${name}.log`)
  const log = createWriteStream(logPath, { flags: 'a' })
  const child = spawn(command, args, { cwd: opts.cwd, env: opts.env, detached: true, stdio: ['ignore', 'pipe', 'pipe'] })
  child.stdout?.pipe(log)
  child.stderr?.pipe(log)
  child.on('exit', (code, signal) => {
    log.write(`\n[stack] ${name} exited (code ${code}, signal ${signal})\n`)
  })
  return { name, child, logPath }
}

export function logTail(service: Service, lines = 40): string {
  try {
    return readFileSync(service.logPath, 'utf8').split('\n').slice(-lines).join('\n')
  } catch {
    return '(no log)'
  }
}

/** Resolves when a one-shot service exits 0; rejects with its log tail otherwise. */
export function exitedCleanly(service: Service): Promise<void> {
  return new Promise((resolve, reject) => {
    service.child.on('error', reject)
    service.child.on('exit', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`${service.name} failed (exit ${code}):\n${logTail(service)}`))
    })
  })
}

function signal(pid: number, name: NodeJS.Signals): void {
  try {
    process.kill(-pid, name)
  } catch {
    // The group is already gone.
  }
}

/** SIGTERM the service's process group; SIGKILL it if it outlives `graceMs`. */
export async function stopService(service: Service, graceMs = 10_000): Promise<void> {
  const { child } = service
  if (child.pid === undefined || child.exitCode !== null || child.signalCode !== null) return
  const exited = new Promise<void>((resolve) => child.once('exit', () => resolve()))
  signal(child.pid, 'SIGTERM')
  const timer = setTimeout(() => signal(child.pid as number, 'SIGKILL'), graceMs)
  await exited
  clearTimeout(timer)
}
