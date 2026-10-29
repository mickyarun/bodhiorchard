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
 * The real API as one member, for the setup steps a test isn't about
 * (creating the BUD whose stages it then moves in the browser, say).
 * Requests go through the dev server's proxy, like the app's own.
 */
import { request, type APIRequestContext } from '@playwright/test'
import { FRONTEND_URL } from '../stack/config.ts'
import { apiLogin, type Member } from './stack.ts'

export class Api {
  private readonly ctx: APIRequestContext

  private constructor(ctx: APIRequestContext) {
    this.ctx = ctx
  }

  static async as(member: Member): Promise<Api> {
    const tokens = await apiLogin(member)
    const ctx = await request.newContext({
      baseURL: `${FRONTEND_URL}/api/v1/`,
      extraHTTPHeaders: { Authorization: `Bearer ${tokens.access}` },
    })
    return new Api(ctx)
  }

  async get<T>(path: string): Promise<T> {
    return this.check<T>('GET', path, await this.ctx.get(path))
  }

  async post<T>(path: string, data: unknown): Promise<T> {
    return this.check<T>('POST', path, await this.ctx.post(path, { data }))
  }

  async patch<T>(path: string, data: unknown): Promise<T> {
    return this.check<T>('PATCH', path, await this.ctx.patch(path, { data }))
  }

  /** Status of a GET, for checks that expect a refusal. */
  async statusOf(path: string): Promise<number> {
    return (await this.ctx.get(path)).status()
  }

  async dispose(): Promise<void> {
    await this.ctx.dispose()
  }

  private async check<T>(method: string, path: string, response: Awaited<ReturnType<APIRequestContext['get']>>): Promise<T> {
    if (!response.ok()) {
      throw new Error(`${method} ${path}: ${response.status()} ${await response.text()}`)
    }
    return (await response.json()) as T
  }
}

export interface Bud {
  id: string
  bud_number: number
  title: string
  status: string
}

export async function createBud(api: Api, title: string, extra: Record<string, unknown> = {}): Promise<Bud> {
  // Trailing slash: the API doesn't redirect slashes.
  return api.post<Bud>('buds/', { title, ...extra })
}
