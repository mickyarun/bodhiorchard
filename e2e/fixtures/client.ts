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
 * One test's handle on its stack: the `/__e2e` seeding and guard routes and
 * the real API. Every request carries the test's id (`x-e2e-test`), so the
 * backend can tag anything the fakes refuse with the test that caused it.
 */
import { randomBytes } from 'node:crypto'
import { request, type APIRequestContext, type APIResponse } from '@playwright/test'
import type { StackTarget } from '../stack/config.ts'
import { Api } from './api.ts'
import type {
  DeliverySpec, FeatureSpec, GuardReport, Member, OrgSpec, QuizSpec, ReleaseSpec, SeededOrg, SeededRepo,
} from './types.ts'

export const TEST_HEADER = 'x-e2e-test'

type SeededWire<K extends string> = Omit<SeededOrg<K>, 'members'> & {
  members: Record<K, Omit<Member, 'password' | 'orgSlug'>>
}

async function body<T>(what: string, response: APIResponse): Promise<T> {
  if (!response.ok()) throw new Error(`${what} failed: ${response.status()} ${await response.text()}`)
  return response.status() === 204 ? (undefined as T) : ((await response.json()) as T)
}

export class StackClient {
  readonly target: StackTarget
  readonly testTag: string
  private readonly backend: APIRequestContext
  private readonly opened: Api[] = []

  private constructor(target: StackTarget, testTag: string, backend: APIRequestContext) {
    this.target = target
    this.testTag = testTag
    this.backend = backend
  }

  static async open(target: StackTarget, testTag: string): Promise<StackClient> {
    const backend = await request.newContext({
      baseURL: target.backendUrl,
      extraHTTPHeaders: { [TEST_HEADER]: testTag },
    })
    return new StackClient(target, testTag, backend)
  }

  /** An org with its members (all sharing one random password) and leave types. */
  async seedOrg<K extends string>(spec: OrgSpec<K>): Promise<SeededOrg<K>> {
    const password = `E2e-${randomBytes(9).toString('base64url')}`
    const org = await body<SeededWire<K>>('seeding an org', await this.backend.post('/__e2e/orgs', { data: { ...spec, password } }))
    const members = Object.fromEntries(
      Object.entries(org.members).map(([key, m]) => [key, { ...(m as object), password, orgSlug: org.slug }]),
    ) as Record<K, Member>
    return { ...org, members }
  }

  async addFeatures(org: SeededOrg, features: FeatureSpec[]): Promise<void> {
    await body('adding features', await this.backend.post(`/__e2e/orgs/${org.id}/features`, { data: { features } }))
  }

  /** Opens today's quiz; the org must have been seeded with `quiz: true`. */
  async openQuiz(org: SeededOrg, quiz: QuizSpec): Promise<void> {
    await body('opening a quiz', await this.backend.post(`/__e2e/orgs/${org.id}/quiz`, { data: quiz }))
  }

  /** A tracked repository (no checkout needed). */
  async addRepo(org: SeededOrg, name: string): Promise<SeededRepo> {
    return body('adding a repo', await this.backend.post(`/__e2e/orgs/${org.id}/repos`, { data: { name } }))
  }

  /**
   * What GitHub would have told the app about a BUD's code: the repos it
   * touches and their PRs. Its manual test cases and release merges below
   * stand in for the QA agent and release detection the same way.
   */
  async setDelivery(org: SeededOrg, budId: string, delivery: DeliverySpec): Promise<void> {
    await body('setting delivery', await this.backend.post(`/__e2e/orgs/${org.id}/buds/${budId}/delivery`, { data: delivery }))
  }

  async setManualCases(org: SeededOrg, budId: string, cases: { id: string, title: string }[]): Promise<void> {
    await body('setting manual cases', await this.backend.post(`/__e2e/orgs/${org.id}/buds/${budId}/manual-cases`, { data: { cases } }))
  }

  async recordRelease(org: SeededOrg, budId: string, release: ReleaseSpec): Promise<void> {
    await body('recording a release', await this.backend.post(`/__e2e/orgs/${org.id}/buds/${budId}/releases`, { data: release }))
  }

  /** Empties the database (only the wizard's stack is ever reset). */
  async reset(): Promise<void> {
    await body('resetting the database', await this.backend.post('/__e2e/reset'))
  }

  /** What the backend refused while serving this test. */
  async guardReport(): Promise<GuardReport> {
    return body('reading the guard report', await this.backend.get('/__e2e/guard', { params: { test: this.testTag } }))
  }

  /** The real login API, as the login page calls it. */
  async login(email: string, password: string, orgSlug: string): Promise<{ access: string, refresh: string }> {
    const api = await request.newContext({ baseURL: this.target.frontendUrl, extraHTTPHeaders: { [TEST_HEADER]: this.testTag } })
    try {
      const tokens = await body<{ access_token: string, refresh_token: string }>(
        `signing in as ${email}`,
        await api.post('/api/v1/auth/login', { data: { email, password, org_slug: orgSlug } }),
      )
      return { access: tokens.access_token, refresh: tokens.refresh_token }
    } finally {
      await api.dispose()
    }
  }

  /** The app's API as `member`, through the dev server's proxy. Closed with the test. */
  async api(member: Member): Promise<Api> {
    const ctx = await request.newContext({
      baseURL: `${this.target.frontendUrl}/api/v1/`,
      extraHTTPHeaders: { Authorization: `Bearer ${member.accessToken}`, [TEST_HEADER]: this.testTag },
    })
    const api = new Api(ctx)
    this.opened.push(api)
    return api
  }

  async dispose(): Promise<void> {
    await Promise.all(this.opened.map((api) => api.dispose()))
    await this.backend.dispose()
  }
}
