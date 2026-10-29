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
 * Talks to the stack outside the browser: the backend's `/__e2e` seeding
 * routes (see backend/tests/e2e_stack/routes.py) and the real login API.
 */
import { randomBytes } from 'node:crypto'
import { request, type APIRequestContext } from '@playwright/test'
import { BACKEND_URL, FRONTEND_URL } from '../stack/config.ts'

export type SystemRole =
  | 'org_owner' | 'admin' | 'hr' | 'manager' | 'pm' | 'tech_lead' | 'developer'
  | 'designer' | 'qa' | 'support' | 'viewer' | 'quiz_master' | 'sales'

export interface MemberSpec {
  key: string
  role?: SystemRole | null
  name?: string
  /** Key of another member who is this member's primary manager. */
  manager?: string
  mustChangePassword?: boolean
  characterModel?: string | null
}

export interface OrgSpec {
  members: MemberSpec[]
  /** Seed into the org the login page signs in to, instead of a new one. */
  primary?: boolean
  quiz?: boolean
  leaveTypes?: { name: string, code: string, quotaDays?: number }[]
  /** Features in the registry, as a scan would have written them. */
  features?: { title: string, description: string, tags?: string[] }[]
  /** Today's quiz, already open (needs `quiz: true`). */
  openQuiz?: { prompt: string, choices: string[], correctIndex: number, explanation?: string }
}

export interface Member {
  id: string
  email: string
  name: string
  password: string
  orgSlug: string
}

export interface SeededOrg<K extends string = string> {
  id: string
  slug: string
  name: string
  members: Record<K, Member>
  leaveTypes: Record<string, string>
}

export interface Tokens {
  access: string
  refresh: string
}

let backend: APIRequestContext | undefined

async function backendApi(): Promise<APIRequestContext> {
  backend ??= await request.newContext({ baseURL: BACKEND_URL })
  return backend
}

async function ok<T>(what: string, response: Awaited<ReturnType<APIRequestContext['get']>>): Promise<T> {
  if (!response.ok()) {
    throw new Error(`${what} failed: ${response.status()} ${await response.text()}`)
  }
  return (await response.json()) as T
}

export async function seedOrg<K extends string>(spec: OrgSpec & { members: (MemberSpec & { key: K })[] }): Promise<SeededOrg<K>> {
  const password = `E2e-${randomBytes(9).toString('base64url')}`
  const api = await backendApi()
  const org = await ok<Omit<SeededOrg<K>, 'members'> & { members: Record<K, Omit<Member, 'password' | 'orgSlug'>> }>(
    'seeding an org',
    await api.post('/__e2e/orgs', { data: { ...spec, password } }),
  )
  const members = Object.fromEntries(
    Object.entries(org.members).map(([key, m]) => [key, { ...(m as object), password, orgSlug: org.slug }]),
  ) as Record<K, Member>
  return { ...org, members }
}

export async function resetDatabase(): Promise<void> {
  const api = await backendApi()
  const response = await api.post('/__e2e/reset')
  if (!response.ok()) throw new Error(`reset failed: ${response.status()}`)
}

export interface GuardReport {
  /** External calls the backend refused. */
  violations: string[]
  /** Agent runs the real CLI would have rejected, or that had no script. */
  agentProblems: string[]
}

export async function guardReport(): Promise<GuardReport> {
  const api = await backendApi()
  return ok<GuardReport>('reading the guard log', await api.get('/__e2e/guard'))
}

/** Signs in through the real login API, as the login page does. */
export async function apiLogin(member: Member): Promise<Tokens> {
  const api = await request.newContext({ baseURL: FRONTEND_URL })
  try {
    const body = await ok<{ access_token: string, refresh_token: string }>(
      `signing in as ${member.email}`,
      await api.post('/api/v1/auth/login', {
        data: { email: member.email, password: member.password, org_slug: member.orgSlug },
      }),
    )
    return { access: body.access_token, refresh: body.refresh_token }
  } finally {
    await api.dispose()
  }
}
