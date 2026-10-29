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
 * Start the throwaway stack and keep it running until SIGINT / SIGTERM:
 * Postgres and Redis in Docker, migrations, the fake-backed backend, the
 * multiplayer server and the Vite dev server. Playwright runs this as its
 * `webServer`; `npm run stack` runs it on its own so repeated test runs can
 * reuse it. Stopping it removes the containers and `.stack/` is rebuilt on
 * the next start.
 */
import { randomBytes } from 'node:crypto'
import { mkdirSync, rmSync } from 'node:fs'
import path from 'node:path'
import {
  BACKEND_URL, FRONTEND_PORT, FRONTEND_URL, MULTIPLAYER_URL, PYTHON, REPO_ROOT, STACK_DIR,
} from './config.ts'
import { removeCheckoutContainers, startPostgres, startRedis } from './docker.ts'
import { backendEnv, frontendEnv, migrateEnv, multiplayerEnv } from './env.ts'
import {
  exitedCleanly, logTail, startService, stopService, type Service, type ServiceOptions,
} from './process.ts'
import { claimStack, recordGroup, releaseStack } from './state.ts'
import { waitForHttp } from './wait.ts'

const BIN = path.join(REPO_ROOT, 'node_modules', '.bin')
const services: Service[] = []
let stopping = false
let stopped: Promise<never> | undefined
// The containers' `docker run` calls, awaited before cleanup so one still in
// flight (an image pull, say) can't create its container after the removal.
let containersStarting: Promise<unknown> = Promise.resolve()

/** Stops everything once; later calls (a second error, a repeated signal) wait for it. */
function shutdown(code: number): Promise<never> {
  stopping = true
  stopped ??= (async () => {
    await Promise.all(services.map((service) => stopService(service)))
    await containersStarting.catch(() => undefined)
    await removeCheckoutContainers()
    releaseStack()
    process.exit(code)
  })()
  return stopped
}

let signals = 0
function onSignal(): void {
  signals += 1
  // npm forwards Ctrl-C and the terminal sends it too: only a third signal
  // means "stop waiting for the cleanup".
  if (signals > 2) process.exit(130)
  void shutdown(0)
}

class StoppingError extends Error {}

function stillStarting(): void {
  if (stopping) throw new StoppingError('the stack is stopping')
}

/** Starts a child; one that fails to spawn or dies early stops the whole stack. */
function launch(name: string, command: string, args: string[], opts: ServiceOptions, longLived = true): Service {
  stillStarting()
  const service = startService(name, command, args, opts)
  services.push(service)
  if (service.child.pid !== undefined) recordGroup(service.child.pid, args.join(' '))
  service.child.on('error', (error) => {
    if (stopping) return
    console.error(`[stack] ${name} could not start: ${error.message}`)
    void shutdown(1)
  })
  if (longLived) {
    service.child.on('exit', (code) => {
      if (stopping) return
      console.error(`[stack] ${name} exited (code ${code}):\n${logTail(service)}`)
      void shutdown(1)
    })
  }
  return service
}

async function main(): Promise<void> {
  await removeCheckoutContainers()
  rmSync(STACK_DIR, { recursive: true, force: true })
  for (const dir of ['logs/backend', 'data', 'uploads', 'home']) {
    mkdirSync(path.join(STACK_DIR, dir), { recursive: true })
  }
  const runId = randomBytes(4).toString('hex')
  const starting = Promise.all([startPostgres(runId), startRedis(runId)])
  containersStarting = starting
  const [pg, redis] = await starting
  stillStarting()
  const ports = { postgres: pg.hostPort, redis: redis.hostPort }
  console.log(`[stack] postgres on :${ports.postgres}, redis on :${ports.redis}`)

  const backendDir = path.join(REPO_ROOT, 'backend')
  await exitedCleanly(launch('migrate', PYTHON, ['-m', 'alembic', 'upgrade', 'head'], {
    cwd: backendDir, env: migrateEnv(ports),
  }, false))
  // The backend runs from .stack/ so it never reads a developer's backend/.env.
  launch('backend', PYTHON, ['-m', 'tests.e2e_stack.serve'], { cwd: STACK_DIR, env: backendEnv(ports) })
  launch('multiplayer', path.join(BIN, 'ts-node'), ['--transpile-only', 'src/main.ts'], {
    cwd: path.join(REPO_ROOT, 'multiplayer'), env: multiplayerEnv(),
  })
  await Promise.all([
    waitForHttp('backend', `${BACKEND_URL}/health/`),
    waitForHttp('multiplayer', MULTIPLAYER_URL),
  ])
  // Vite starts last: Playwright (and a reused stack) treats "the frontend
  // answers" as "the whole stack is up".
  // --force: a cold dependency cache on every start, so a screen that makes
  // Vite re-optimise mid-run shows up (see fixtures/global-teardown.ts).
  launch('frontend', path.join(BIN, 'vite'), [
    '--port', String(FRONTEND_PORT), '--strictPort', '--host', '127.0.0.1', '--force',
  ], { cwd: path.join(REPO_ROOT, 'frontend'), env: frontendEnv() })
  await waitForHttp('frontend', FRONTEND_URL)
  stillStarting()
  console.log(`[stack] ready: ${FRONTEND_URL} (logs in ${path.relative(REPO_ROOT, STACK_DIR)}/logs)`)
}

function fail(error: unknown): void {
  if (stopping || error instanceof StoppingError) return
  console.error(`[stack] failed: ${error instanceof Error ? error.message : String(error)}`)
  void shutdown(1)
}

// Claim first: when another runner owns this checkout's stack, leave
// without touching it (no cleanup handlers are installed yet).
try {
  claimStack()
} catch (error) {
  console.error(`[stack] ${error instanceof Error ? error.message : String(error)}`)
  process.exit(1)
}
process.on('SIGINT', onSignal)
process.on('SIGTERM', onSignal)
process.on('uncaughtException', fail)
process.on('unhandledRejection', fail)
main().catch(fail)
