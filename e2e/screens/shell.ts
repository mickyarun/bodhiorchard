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
 * The app shell every signed-in screen shares: the sidebar and the
 * account menu. Names are matched exactly: role names match substrings
 * otherwise, and "Board" would also find "Dashboard" and "Leaderboard".
 */
import { expect, type Locator, type Page } from '@playwright/test'

export function sidebar(page: Page): Locator {
  return page.getByRole('navigation').first()
}

export function navLink(page: Page, name: string): Locator {
  return sidebar(page).getByRole('link', { name, exact: true })
}

/** Expands the sidebar's Settings group, which lists only links the member may open. */
export async function openSettingsGroup(page: Page): Promise<void> {
  const opener = sidebar(page).getByRole('button', { name: 'Settings', exact: true })
  await opener.click()
  await expect(opener).toHaveAttribute('aria-expanded', 'true')
}

export async function signOut(page: Page, name: string): Promise<void> {
  await page.getByRole('button', { name: `Account menu for ${name}` }).click()
  // The menu's items render as list items, not menu items.
  await page.getByRole('listitem').filter({ hasText: 'Sign out' }).click()
}

/**
 * Resolves once the page's live room has sent it something: the
 * multiplayer socket (through the dev proxy) is open and answering. Start
 * it before the navigation that opens the room.
 */
export async function liveRoomAnswers(page: Page): Promise<void> {
  const socket = await page.waitForEvent('websocket', (ws) => ws.url().includes('/colyseus/'))
  await socket.waitForEvent('framereceived')
}
