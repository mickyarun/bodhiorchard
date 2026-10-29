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
 * The app's real API as one member (get one from `stack.api(member)`), for
 * the setup steps a test isn't about: creating the BUD whose stages it then
 * moves in the browser, say. Requests go through the dev server's proxy,
 * like the app's own.
 */
import type { APIRequestContext, APIResponse } from '@playwright/test'
import type { LeaveDays } from './dates.ts'

export class Api {
  private readonly ctx: APIRequestContext

  constructor(ctx: APIRequestContext) {
    this.ctx = ctx
  }

  async get<T>(path: string): Promise<T> {
    return this.check<T>('GET', path, await this.ctx.get(path))
  }

  async post<T>(path: string, data: unknown): Promise<T> {
    return this.check<T>('POST', path, await this.ctx.post(path, { data }))
  }

  /** Status of a GET, for checks that expect a refusal. */
  async statusOf(path: string): Promise<number> {
    return (await this.ctx.get(path)).status()
  }

  async dispose(): Promise<void> {
    await this.ctx.dispose()
  }

  private async check<T>(method: string, path: string, response: APIResponse): Promise<T> {
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

/** A BUD with every stage agent off (the API's default). */
export function createBud(api: Api, title: string): Promise<Bud> {
  // Trailing slash: the API doesn't redirect slashes.
  return api.post<Bud>('buds/', { title })
}

export interface LeaveRequest {
  id: string
  status: string
}

export function requestLeave(api: Api, leaveTypeId: string, days: LeaveDays, reason: string): Promise<LeaveRequest> {
  return api.post<LeaveRequest>('leave/requests', {
    kind: 'leave', leave_type_id: leaveTypeId, start_date: days.from, end_date: days.to, reason,
  })
}

export async function approveLeave(api: Api, requestId: string): Promise<void> {
  await api.post(`leave/requests/${requestId}/approve`, {})
}
