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
 * The stack's own Postgres and Redis containers. Each one gets a unique
 * name and a label naming this checkout, and its host port is picked by
 * Docker on loopback, so a run never touches (or collides with) another
 * database. Cleanup goes by the label, so it also finds containers a run
 * that was killed outright left behind.
 */
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { CHECKOUT_ID } from './config.ts'
import { waitFor } from './wait.ts'

const run = promisify(execFile)
const LABEL = `glideship-e2e.checkout=${CHECKOUT_ID}`

export const PG_USER = 'e2e'
export const PG_PASSWORD = 'e2e'
export const PG_DB = 'glideship_e2e'

export interface Container {
  name: string
  hostPort: number
}

async function docker(...args: string[]): Promise<string> {
  const { stdout } = await run('docker', args, { maxBuffer: 1 << 20 })
  return stdout.trim()
}

async function start(name: string, image: string, containerPort: number, env: string[]): Promise<Container> {
  const envArgs = env.flatMap((pair) => ['-e', pair])
  await docker(
    'run', '-d', '--rm', '--name', name, '--label', LABEL,
    '-p', `127.0.0.1::${containerPort}`, ...envArgs, image,
  )
  const mapping = await docker('port', name, `${containerPort}/tcp`)
  return { name, hostPort: Number(mapping.split('\n')[0].split(':').pop()) }
}

export async function startPostgres(runId: string): Promise<Container> {
  const pg = await start(`glideship-e2e-pg-${runId}`, 'pgvector/pgvector:pg16', 5432, [
    `POSTGRES_USER=${PG_USER}`,
    `POSTGRES_PASSWORD=${PG_PASSWORD}`,
    `POSTGRES_DB=${PG_DB}`,
  ])
  // The image's init runs a socket-only server first and then restarts, so
  // only a TCP query proves the real server is up.
  await waitFor('postgres', async () => {
    await docker('exec', pg.name, 'psql', '-h', '127.0.0.1', '-U', PG_USER, '-d', PG_DB, '-c', 'select 1')
    return true
  })
  return pg
}

export async function startRedis(runId: string): Promise<Container> {
  const redis = await start(`glideship-e2e-redis-${runId}`, 'redis:7-alpine', 6379, [])
  await waitFor('redis', async () => (await docker('exec', redis.name, 'redis-cli', 'ping')) === 'PONG')
  return redis
}

/** Removes every container of this checkout's stack, running or not. */
export async function removeCheckoutContainers(): Promise<void> {
  const ids = await docker('ps', '-aq', '--filter', `label=${LABEL}`).catch(() => '')
  if (ids) await docker('rm', '-f', ...ids.split('\n')).catch(() => undefined)
}
