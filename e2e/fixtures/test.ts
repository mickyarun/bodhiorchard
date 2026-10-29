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
 * The `test` every spec imports. On top of Playwright's own fixtures:
 *
 * - every browser context stays inside the stack (see `browser.ts`);
 * - `signedIn(member)` opens a new window already signed in as `member`,
 *   through the real login API, so two people can act in one test;
 * - after each test it fails on requests that left the stack, uncaught page
 *   errors, external calls the backend's guard refused, and agent runs the
 *   fake CLI flagged, meanwhile.
 */
import { test as base, expect, type BrowserContext, type Page } from '@playwright/test'
import { FRONTEND_URL } from '../stack/config.ts'
import { keepInsideStack, newBrowserLog, type BrowserLog } from './browser.ts'
import { apiLogin, guardReport, type Member } from './stack.ts'

export const TOKEN_KEY = 'bodhiorchard_token'
export const REFRESH_TOKEN_KEY = 'bodhiorchard_refresh_token'

interface Fixtures {
  browserLog: BrowserLog
  signedIn: (member: Member) => Promise<Page>
  stackGuard: void
}

export const test = base.extend<Fixtures>({
  browserLog: async ({}, use) => {
    await use(newBrowserLog())
  },

  context: async ({ context, browserLog }, use) => {
    await keepInsideStack(context, browserLog)
    await use(context)
  },

  signedIn: async ({ browser, browserLog }, use) => {
    const contexts: BrowserContext[] = []
    await use(async (member) => {
      const tokens = await apiLogin(member)
      const context = await browser.newContext({
        baseURL: FRONTEND_URL,
        storageState: {
          cookies: [],
          origins: [{
            origin: FRONTEND_URL,
            localStorage: [
              { name: TOKEN_KEY, value: tokens.access },
              { name: REFRESH_TOKEN_KEY, value: tokens.refresh },
            ],
          }],
        },
      })
      contexts.push(context)
      await keepInsideStack(context, browserLog)
      return context.newPage()
    })
    await Promise.all(contexts.map((context) => context.close()))
  },

  stackGuard: [
    async ({ browserLog }, use) => {
      const before = await guardReport()
      await use()
      expect(browserLog.external, 'browser requests that left the stack').toEqual([])
      expect(browserLog.pageErrors, 'uncaught errors in the page').toEqual([])
      // Both lists only grow; new entries came from this test or one beside it.
      const after = await guardReport()
      expect(after.violations.slice(before.violations.length), 'external calls the backend refused').toEqual([])
      expect(after.agentProblems.slice(before.agentProblems.length), 'agent runs the fake CLI flagged').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
