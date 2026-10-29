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
  BACKEND_PORT, BACKEND_URL, FRONTEND_URL, GUARD_LOG, MULTIPLAYER_PORT, MULTIPLAYER_URL,
  REPO_ROOT, STACK_DIR, STACK_HOME,
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

export function databaseUrl(ports: StackPorts): string {
  return `postgresql+asyncpg://${PG_USER}:${PG_PASSWORD}@127.0.0.1:${ports.postgres}/${PG_DB}`
}

const BRIDGE_SECRET = secret()

export function backendEnv(ports: StackPorts): NodeJS.ProcessEnv {
  return {
    ...base(),
    HOME: STACK_HOME,
    PYTHONPATH: path.join(REPO_ROOT, 'backend'),
    PYTHONUNBUFFERED: '1',
    ENV: 'dev',
    DATABASE_URL: databaseUrl(ports),
    REDIS_URL: `redis://127.0.0.1:${ports.redis}/0`,
    SECRET_KEY: secret(),
    ENCRYPTION_KEY: secret(),
    HR_ENCRYPTION_KEYS: `e2e:${randomBytes(32).toString('base64')}`,
    COLYSEUS_URL: MULTIPLAYER_URL,
    COLYSEUS_BRIDGE_SECRET: BRIDGE_SECRET,
    PUBLIC_URL: BACKEND_URL,
    MCP_BACKEND_URL: BACKEND_URL,
    FRONTEND_URL,
    BODHIORCHARD_DATA_DIR: path.join(STACK_DIR, 'data'),
    FILE_STORAGE_LOCAL_DIR: path.join(STACK_DIR, 'uploads'),
    LOG_DIR: path.join(STACK_DIR, 'logs', 'backend'),
    // Blank on purpose: an empty value beats anything in a backend/.env file.
    SLACK_BOT_TOKEN: '',
    SLACK_SIGNING_SECRET: '',
    GIPHY_API_KEY: '',
    GITHUB_PAT: '',
    HF_HUB_OFFLINE: '1',
    E2E_BACKEND_PORT: String(BACKEND_PORT),
    E2E_GUARD_LOG: GUARD_LOG,
  }
}

export function migrateEnv(ports: StackPorts): NodeJS.ProcessEnv {
  return { ...base(), DATABASE_URL: databaseUrl(ports), PYTHONUNBUFFERED: '1' }
}

export function multiplayerEnv(): NodeJS.ProcessEnv {
  return {
    ...base(),
    PORT: String(MULTIPLAYER_PORT),
    BACKEND_URL,
    COLYSEUS_BRIDGE_SECRET: BRIDGE_SECRET,
    NODE_ENV: 'development',
  }
}

export function frontendEnv(): NodeJS.ProcessEnv {
  return {
    ...base(),
    VITE_API_TARGET: BACKEND_URL,
    VITE_COLYSEUS_TARGET: MULTIPLAYER_URL,
    // Same-origin paths through the dev proxy, as in local development. Vite
    // lets these beat a frontend/.env that points at a developer's servers.
    VITE_API_BASE_URL: '/api',
    VITE_COLYSEUS_URL: '',
  }
}
