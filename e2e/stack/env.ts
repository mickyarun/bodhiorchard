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
 * Environment for each stack process. Children start from a short allowlist
 * of the caller's variables, never the whole shell, so a developer's real
 * Slack, GitHub or Claude credentials can't leak into the test backend.
 * Every secret is random per run.
 */
import { randomBytes } from 'node:crypto'
import path from 'node:path'
import {
  MAIN_STACK, REPO_ROOT, STACK_DIR, STACK_HOME, type StackTarget,
} from './config.ts'
import { PG_DB, PG_PASSWORD, PG_USER } from './docker.ts'

const PASSTHROUGH = ['PATH', 'HOME', 'USER', 'SHELL', 'LANG', 'LC_ALL', 'TMPDIR', 'TERM', 'CI']

function base(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {}
  for (const key of PASSTHROUGH) {
    if (process.env[key] !== undefined) env[key] = process.env[key]
  }
  return env
}

const secret = (bytes = 32): string => randomBytes(bytes).toString('base64url')

export interface StackPorts {
  postgres: number
  redis: number
}

export function databaseUrl(ports: StackPorts, database: string = PG_DB): string {
  return `postgresql+asyncpg://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${ports.postgres}/${database}`
}

const BRIDGE_SECRET = secret()

export function backendEnv(ports: StackPorts, target: StackTarget): NodeJS.ProcessEnv {
  const own = (dir: string): string => path.join(STACK_DIR, dir, target.name)
  return {
    ...base(),
    HOME: STACK_HOME,
    PYTHONPATH: path.join(REPO_ROOT, 'backend'),
    PYTHONUNBUFFERED: '1',
    ENV: 'dev',
    DATABASE_URL: databaseUrl(ports, target.database),
    // One Redis, a database number each, so the two job queues never mix.
    REDIS_URL: `redis://127.0.0.1:${ports.redis}/${target === MAIN_STACK ? 0 : 1}`,
    SECRET_KEY: secret(),
    ENCRYPTION_KEY: secret(),
    HR_ENCRYPTION_KEYS: `e2e:${randomBytes(32).toString('base64')}`,
    COLYSEUS_URL: target.multiplayerUrl,
    COLYSEUS_BRIDGE_SECRET: BRIDGE_SECRET,
    PUBLIC_URL: target.backendUrl,
    MCP_BACKEND_URL: target.backendUrl,
    FRONTEND_URL: target.frontendUrl,
    BODHIORCHARD_DATA_DIR: own('data'),
    FILE_STORAGE_LOCAL_DIR: own('uploads'),
    LOG_DIR: own('logs'),
    // Blank on purpose: an empty value beats anything in a backend/.env file.
    SLACK_BOT_TOKEN: '',
    SLACK_SIGNING_SECRET: '',
    GIPHY_API_KEY: '',
    GITHUB_PAT: '',
    HF_HUB_OFFLINE: '1',
    E2E_BACKEND_PORT: String(target.backendPort),
    E2E_GUARD_LOG: target.guardLog,
  }
}

export function migrateEnv(ports: StackPorts, target: StackTarget): NodeJS.ProcessEnv {
  return { ...base(), DATABASE_URL: databaseUrl(ports, target.database), PYTHONUNBUFFERED: '1' }
}

export function multiplayerEnv(target: StackTarget): NodeJS.ProcessEnv {
  return {
    ...base(),
    PORT: String(target.multiplayerPort),
    BACKEND_URL: target.backendUrl,
    COLYSEUS_BRIDGE_SECRET: BRIDGE_SECRET,
    NODE_ENV: 'development',
  }
}

export function frontendEnv(target: StackTarget): NodeJS.ProcessEnv {
  return {
    ...base(),
    VITE_API_TARGET: target.backendUrl,
    VITE_CACHE_DIR: target.viteCacheDir,
    VITE_COLYSEUS_TARGET: target.multiplayerUrl,
    // Same-origin paths through the dev proxy, as in local development. Vite
    // lets these beat a frontend/.env that points at a developer's servers.
    VITE_API_BASE_URL: '/api',
    VITE_COLYSEUS_URL: '',
  }
}
