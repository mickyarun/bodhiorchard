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
 * Keeps a browser context inside the stack. The page only ever talks to
 * this checkout's frontend origin (its dev proxy forwards the API and
 * multiplayer). Requests to anything else, a developer's own servers on
 * other loopback ports included, are refused and recorded, and so are
 * websockets (the test then fails), except Google Fonts, which get an
 * empty stylesheet so pages render the same offline. Uncaught page errors and
 * console errors are collected for the test to check.
 */
import type { BrowserContext, ConsoleMessage, Page } from '@playwright/test'
import type { StackTarget } from '../stack/config.ts'

/** The `host:port` forms a page may load from: the target's frontend only. */
export function stackOrigins(target: StackTarget): Set<string> {
  return new Set([`127.0.0.1:${target.frontendPort}`, `localhost:${target.frontendPort}`])
}

const FONT_HOSTS = new Set(['fonts.googleapis.com', 'fonts.gstatic.com'])

export interface BrowserLog {
  /** Requests that tried to leave the stack. */
  external: string[]
  /** Uncaught exceptions thrown in a page. */
  pageErrors: string[]
  /** `console.error` lines, with the page URL. */
  consoleErrors: string[]
}

export function newBrowserLog(): BrowserLog {
  return { external: [], pageErrors: [], consoleErrors: [] }
}

function describe(message: ConsoleMessage): string {
  const where = message.location().url
  return where ? `${message.text()} (${where})` : message.text()
}

export async function keepInsideStack(context: BrowserContext, log: BrowserLog, target: StackTarget): Promise<void> {
  const origins = stackOrigins(target)
  await context.route(
    (url) => !origins.has(url.host),
    async (route) => {
      const url = new URL(route.request().url())
      if (FONT_HOSTS.has(url.hostname)) {
        await route.fulfill({ status: 200, contentType: 'text/css', body: '' })
        return
      }
      log.external.push(`${route.request().method()} ${url.origin}${url.pathname}`)
      await route.abort('blockedbyclient')
    },
  )
  const watch = (page: Page): void => {
    // Websockets can only be recorded, not refused: routeWebSocket swaps in
    // a WebSocket shim stricter than the browser's, which breaks the app's
    // own sockets. A socket to anywhere else still fails the test.
    page.on('websocket', (ws) => {
      if (!origins.has(new URL(ws.url()).host)) log.external.push(`WS ${ws.url()}`)
    })
    page.on('pageerror', (error) => log.pageErrors.push(error.stack ?? error.message))
    page.on('console', (message) => {
      if (message.type() === 'error') log.consoleErrors.push(describe(message))
    })
  }
  context.pages().forEach(watch)
  context.on('page', watch)
}
