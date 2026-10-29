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
 * Where the throwaway stack listens, shared by `run.ts` and the Playwright
 * config. Every port is off the defaults of a developer's own stack (3000,
 * 8000, 2567, 5432, 6379), and each checkout gets its own block (from a
 * hash of its path), so two worktrees never share or reset one stack. Any
 * port can be moved with an env var. Postgres and Redis get a free port
 * from Docker.
 */
import { createHash } from 'node:crypto'
import { realpathSync } from 'node:fs'
import path from 'node:path'

// Symlinks resolved, as the backend's own path is (see /__e2e/identity).
export const REPO_ROOT = realpathSync(path.resolve(import.meta.dirname, '..', '..'))
/** Short, stable id of this checkout: ports, container labels. */
export const CHECKOUT_ID = createHash('sha256').update(REPO_ROOT).digest('hex').slice(0, 12)
const PORT_OFFSET = Number.parseInt(CHECKOUT_ID.slice(0, 6), 16) % 1000

function port(name: string, base: number): number {
  const raw = process.env[name]
  const value = raw ? Number(raw) : base + PORT_OFFSET
  if (!Number.isInteger(value) || value < 1024 || value > 65535) {
    throw new Error(`${name} must be a port number, got ${raw}`)
  }
  return value
}

/** Logs, uploads, clones and the guard logs of one stack run (gitignored). */
export const STACK_DIR = path.join(REPO_ROOT, 'e2e', '.stack')

/**
 * One backend, its database, its multiplayer server and the Vite server in
 * front of them. `main` serves every spec; `wizard` serves only the setup
 * wizard, which needs an empty database, so no spec has to wait for it or
 * run in its shadow.
 */
export interface StackTarget {
  name: 'main' | 'wizard'
  frontendPort: number
  backendPort: number
  multiplayerPort: number
  frontendUrl: string
  backendUrl: string
  multiplayerUrl: string
  database: string
  guardLog: string
  /** Its own dependency cache, never the one a dev server in this checkout uses. */
  viteCacheDir: string
}

interface Ports {
  frontend: number
  backend: number
  multiplayer: number
}

function target(name: StackTarget['name'], ports: Ports, database: string): StackTarget {
  return {
    name,
    frontendPort: ports.frontend,
    backendPort: ports.backend,
    multiplayerPort: ports.multiplayer,
    frontendUrl: `http://127.0.0.1:${ports.frontend}`,
    backendUrl: `http://127.0.0.1:${ports.backend}`,
    multiplayerUrl: `http://127.0.0.1:${ports.multiplayer}`,
    database,
    guardLog: path.join(STACK_DIR, `guard-${name}.log`),
    viteCacheDir: path.join(STACK_DIR, `vite-${name}`),
  }
}

export const MAIN_STACK = target('main', {
  frontend: port('E2E_FRONTEND_PORT', 13000),
  backend: port('E2E_BACKEND_PORT', 14000),
  multiplayer: port('E2E_MULTIPLAYER_PORT', 15000),
}, 'glideship_e2e')
export const WIZARD_STACK = target('wizard', {
  frontend: port('E2E_WIZARD_FRONTEND_PORT', 16000),
  backend: port('E2E_WIZARD_BACKEND_PORT', 17000),
  multiplayer: port('E2E_WIZARD_MULTIPLAYER_PORT', 18000),
}, 'glideship_e2e_wizard')
export const STACKS: readonly StackTarget[] = [MAIN_STACK, WIZARD_STACK]

/**
 * The backend's home directory. The repo picker only accepts paths under
 * home, so specs create their git repos here, and the backend never reads
 * the developer's own home.
 */
export const STACK_HOME = path.join(STACK_DIR, 'home')
/**
 * Who owns this checkout's stack, and its process groups. Kept outside
 * `.stack/` (which each start wipes) so a run that was killed outright is
 * cleaned up by the next one (see state.ts).
 */
export const STATE_FILE = path.join(REPO_ROOT, 'e2e', '.stack-state.json')

/** The Python that has the backend's dependencies installed. */
export const PYTHON = process.env.E2E_PYTHON ?? 'python'
