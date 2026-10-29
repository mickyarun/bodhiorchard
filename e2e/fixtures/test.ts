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
 * - `stackTarget` (an option, set per project) says which backend and
 *   frontend the test runs against;
 * - `stack` seeds data and calls the API for this test (see client.ts);
 * - `signedIn(member)` opens a new window already signed in as `member`
 *   (the seed route minted the tokens), so two people can act in one test;
 * - every browser context stays inside the stack (see browser.ts) and tags
 *   its requests with the test's id;
 * - after each test it fails on requests that left the stack, uncaught page
 *   errors, and anything the backend's fakes refused while serving this
 *   test: external calls, and agent runs the real CLI would have rejected.
 */
import { test as base, expect, type BrowserContext, type Page } from '@playwright/test'
import { MAIN_STACK, type StackTarget } from '../stack/config.ts'
import { keepInsideStack, newBrowserLog, type BrowserLog } from './browser.ts'
import { StackClient, TEST_HEADER } from './client.ts'
import type { Member } from './types.ts'

export const TOKEN_KEY = 'bodhiorchard_token'
export const REFRESH_TOKEN_KEY = 'bodhiorchard_refresh_token'

interface Options {
  stackTarget: StackTarget
}

interface Fixtures {
  testTag: string
  stack: StackClient
  browserLog: BrowserLog
  signedIn: (member: Member) => Promise<Page>
  stackGuard: void
}

export const test = base.extend<Options & Fixtures>({
  stackTarget: [MAIN_STACK, { option: true }],

  // Unique per run of a test, repeats and retries included.
  testTag: async ({}, use, testInfo) => {
    await use(`${testInfo.testId}#${testInfo.repeatEachIndex}#${testInfo.retry}`)
  },

  stack: async ({ stackTarget, testTag }, use) => {
    const client = await StackClient.open(stackTarget, testTag)
    await use(client)
    await client.dispose()
  },

  browserLog: async ({}, use) => {
    await use(newBrowserLog())
  },

  context: async ({ context, browserLog, stackTarget, testTag }, use) => {
    await context.setExtraHTTPHeaders({ [TEST_HEADER]: testTag })
    await keepInsideStack(context, browserLog, stackTarget)
    await use(context)
  },

  signedIn: async ({ browser, browserLog, stackTarget, testTag }, use) => {
    const contexts: BrowserContext[] = []
    await use(async (member) => {
      const context = await browser.newContext({
        baseURL: stackTarget.frontendUrl,
        extraHTTPHeaders: { [TEST_HEADER]: testTag },
        storageState: {
          cookies: [],
          origins: [{
            origin: stackTarget.frontendUrl,
            localStorage: [
              { name: TOKEN_KEY, value: member.accessToken },
              { name: REFRESH_TOKEN_KEY, value: member.refreshToken },
            ],
          }],
        },
      })
      contexts.push(context)
      await keepInsideStack(context, browserLog, stackTarget)
      return context.newPage()
    })
    await Promise.all(contexts.map((context) => context.close()))
  },

  stackGuard: [
    async ({ browserLog, stack }, use) => {
      await use()
      expect(browserLog.external, 'browser requests that left the stack').toEqual([])
      expect(browserLog.pageErrors, 'uncaught errors in the page').toEqual([])
      const report = await stack.guardReport()
      expect(report.violations, 'external calls the backend refused').toEqual([])
      expect(report.agentProblems, 'agent runs the fake CLI flagged').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
