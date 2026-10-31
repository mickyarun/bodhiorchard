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
 * The dashboard's Garden Games, and a player for Firefly Follow: the one
 * game that is plain buttons, so a test can play it for real against the
 * multiplayer server, which records the score.
 */
import { expect, type Locator, type Page } from '@playwright/test'

const PADS = ['emerald', 'amber', 'rose', 'sky']

export async function openGames(page: Page): Promise<Locator> {
  await page.goto('/dashboard')
  await page.getByRole('button', { name: /^Games/ }).click()
  const hub = page.getByRole('dialog').filter({ hasText: 'Garden Games' })
  await expect(hub).toBeVisible()
  return hub
}

/**
 * Records every pad that lights while the board shows a sequence. Watches
 * the whole page, so it must be called before the game opens: the first
 * flash can come the moment the board appears.
 */
export async function watchFlashes(page: Page): Promise<void> {
  await page.evaluate(() => {
    const flashes: string[] = []
    Object.assign(window, { e2eFlashes: flashes })
    new MutationObserver((changes) => {
      for (const change of changes) {
        const pad = change.target as HTMLElement
        const watching = pad.closest('.firefly__grid')?.classList.contains('firefly__grid--watch')
        if (pad.classList.contains('firefly__pad--lit') && watching) {
          flashes.push(pad.getAttribute('aria-label') ?? '')
        }
      }
    }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] })
  })
}

/**
 * Taps a pad, then waits for its glow to fade. The server drops taps closer
 * together than a person can press (an anti-bot rule), and the glow lasts
 * longer than that gap, so waiting for it keeps to a human pace.
 */
async function tapPad(page: Page, pad: string): Promise<void> {
  const button = page.getByRole('button', { name: pad, exact: true })
  await button.click()
  await expect(button).not.toHaveClass(/firefly__pad--lit/)
}

async function takeFlashes(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const store = window as unknown as { e2eFlashes: string[] }
    return store.e2eFlashes.splice(0)
  })
}

/**
 * Plays Firefly Follow (call watchFlashes first): clears `levels` levels,
 * then misses on purpose. Each level replays the last sequence plus one new
 * pad, and only that new, last flash is read: an earlier one can be hidden
 * when it lights the pad the player's own tap is still lighting.
 */
export async function playFirefly(page: Page, levels: number): Promise<void> {
  await expect(page.locator('.firefly__grid')).toBeVisible()
  const yourTurn = page.getByText('Your turn', { exact: true })
  const known: string[] = []
  for (let level = 1; level <= levels; level += 1) {
    await expect(yourTurn).toBeVisible({ timeout: 20_000 })
    const flashes = await takeFlashes(page)
    expect(flashes.length, `level ${level} shows a sequence`).toBeGreaterThan(0)
    known.push(flashes[flashes.length - 1])
    for (const pad of known) await tapPad(page, pad)
    await expect(page.locator('.firefly__level')).toContainText(`best ${level}`)
  }
  await expect(yourTurn).toBeVisible({ timeout: 20_000 })
  await takeFlashes(page)
  // Any pad but the first of the known sequence ends the run.
  await page.getByRole('button', { name: PADS.find((pad) => pad !== known[0]), exact: true }).click()
  await expect(page.getByText(`You cleared ${levels} ${levels === 1 ? 'level' : 'levels'}!`)).toBeVisible()
  await page.getByRole('button', { name: 'Collect points' }).click()
}
