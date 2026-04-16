/**
 * BUD-001 Notification Bell — Smoke Gate (17 tests)
 *
 * Covers the merge-blocking subset:
 *   TC-001, TC-002, TC-004, TC-005  — bell + badge rendering
 *   TC-009, TC-010, TC-011, TC-012  — panel open/close
 *   TC-017, TC-018                  — mark-read button + optimistic update
 *   TC-022                          — mark all read
 *   TC-024                          — dismiss single
 *   TC-027, TC-028, TC-029          — clear all confirm flow
 *   TC-032, TC-045                  — error snackbar
 *
 * All tests mock the notifications API via page.route so they run without
 * the taskflow-api backend. An access_token is seeded via addInitScript.
 */
import { test, expect } from '@playwright/test'
import { NotificationBellPage } from '../../src/pages/NotificationBellPage'
import {
  setupNotificationRoutes,
  buildUnread,
  seedAuthToken,
} from '../../src/helpers/notification-mocks'

test.describe('BUD-001 Notification Bell — Smoke', () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthToken(page)
  })

  // ─── TC-001 ──────────────────────────────────────────────────────────────
  test('TC-001: bell renders outline SVG when unread count is zero', async ({ page }) => {
    await setupNotificationRoutes(page, { items: [] })
    const bell = new NotificationBellPage(page)
    await bell.goto()

    await expect(bell.bellSvg).toHaveAttribute('fill', 'none')
    await expect(bell.bellSvg).toHaveAttribute('stroke', 'currentColor')
    await expect(bell.badge).toHaveCount(0)
  })

  // ─── TC-002 ──────────────────────────────────────────────────────────────
  test('TC-002: bell renders filled SVG and badge "3" when 3 unread exist', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(3) })
    const bell = new NotificationBellPage(page)
    await bell.goto()

    await expect(bell.bellSvg).toHaveAttribute('fill', 'currentColor')
    await expect(bell.bellSvg).not.toHaveAttribute('stroke', /.*/)
    await expect(bell.badge).toBeVisible()
    await expect(bell.badge).toHaveText('3')
  })

  // ─── TC-004 ──────────────────────────────────────────────────────────────
  test('TC-004: badge shows exact count for 99 unread', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(99) })
    const bell = new NotificationBellPage(page)
    await bell.goto()

    await expect(bell.badge).toHaveText('99')
  })

  // ─── TC-005 ──────────────────────────────────────────────────────────────
  test('TC-005: badge displays "99+" when unread count is exactly 100', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(100) })
    const bell = new NotificationBellPage(page)
    await bell.goto()

    await expect(bell.badge).toHaveText('99+')
  })

  // ─── TC-009 ──────────────────────────────────────────────────────────────
  test('TC-009: clicking bell opens the notification panel', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(1) })
    const bell = new NotificationBellPage(page)
    await bell.goto()

    await expect(bell.bellButton).toHaveAttribute('aria-expanded', 'false')
    await bell.openPanel()

    await expect(bell.panel).toBeVisible()
    await expect(bell.bellButton).toHaveAttribute('aria-expanded', 'true')
  })

  // ─── TC-010 ──────────────────────────────────────────────────────────────
  test('TC-010: clicking bell a second time closes the panel', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(1) })
    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()
    await expect(bell.panel).toBeVisible()

    // closePanelByBell uses force:true to click through the overlay-backdrop
    await bell.closePanelByBell()

    await expect(bell.panel).toHaveCount(0)
    await expect(bell.bellButton).toHaveAttribute('aria-expanded', 'false')
  })

  // ─── TC-011 ──────────────────────────────────────────────────────────────
  test('TC-011: clicking the backdrop closes the panel', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(1) })
    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()
    await expect(bell.backdrop).toBeVisible()

    await bell.closePanelByBackdrop()

    await expect(bell.panel).toHaveCount(0)
  })

  // ─── TC-012 ──────────────────────────────────────────────────────────────
  test('TC-012: pressing Escape while panel is open closes it', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(1) })
    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()
    await expect(bell.panel).toBeVisible()

    await bell.closePanelByEscape()

    await expect(bell.panel).toHaveCount(0)
  })

  // ─── TC-017 ──────────────────────────────────────────────────────────────
  test('TC-017: mark-read button present on unread items, absent on read items', async ({ page }) => {
    const items = [
      { id: 1, type: 'task_assigned' as const, title: 'Unread one', body: '', time: '', is_read: false },
      { id: 2, type: 'task_assigned' as const, title: 'Read one',   body: '', time: '', is_read: true  },
    ]
    await setupNotificationRoutes(page, { items })
    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()

    await expect(bell.items).toHaveCount(2)
    const unreadItem = bell.items.nth(0)
    const readItem = bell.items.nth(1)

    await expect(unreadItem.locator('.action-btn.mark-read')).toHaveCount(1)
    await expect(readItem.locator('.action-btn.mark-read')).toHaveCount(0)
  })

  // ─── TC-018 ──────────────────────────────────────────────────────────────
  test('TC-018: clicking mark-read removes unread highlight immediately (optimistic)', async ({ page }) => {
    await setupNotificationRoutes(page, {
      items: buildUnread(1),
      patchReadDelayMs: 500,
    })
    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()

    const item = bell.items.nth(0)
    await expect(item).toHaveClass(/\bunread\b/)
    await expect(bell.badge).toHaveText('1')

    await bell.markItemRead(0)

    // Assert within 200ms — well before the 500ms PATCH delay resolves,
    // proving the update is optimistic (pre-server-response).
    await expect(item).not.toHaveClass(/\bunread\b/, { timeout: 200 })
    await expect(item.locator('.action-btn.mark-read')).toHaveCount(0, { timeout: 200 })
    await expect(bell.badge).toHaveCount(0, { timeout: 200 })
  })

  // ─── TC-022 ──────────────────────────────────────────────────────────────
  test('TC-022: clicking "Mark all read" marks all items as read', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(3) })
    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()
    await expect(bell.unreadItems).toHaveCount(3)

    await bell.markAllReadButton.click()

    await expect(bell.unreadItems).toHaveCount(0)
    await expect(bell.badge).toHaveCount(0)
  })

  // ─── TC-024 ──────────────────────────────────────────────────────────────
  test('TC-024: dismiss button removes notification from list immediately', async ({ page }) => {
    const items = [
      { id: 1, type: 'task_assigned' as const, title: 'First',  body: '', time: '', is_read: false },
      { id: 2, type: 'task_assigned' as const, title: 'Second', body: '', time: '', is_read: false },
    ]
    await setupNotificationRoutes(page, { items })
    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()
    await expect(bell.items).toHaveCount(2)

    await bell.dismissItem(0)

    await expect(bell.items).toHaveCount(1)
    await expect(bell.items.nth(0)).toContainText('Second')
  })

  // ─── TC-027 ──────────────────────────────────────────────────────────────
  test('TC-027: first click on "Clear all" shows confirm row; DELETE not called yet', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(1) })

    let deleteCollectionCalls = 0
    page.on('request', (req) => {
      if (req.method() === 'DELETE' && req.url().endsWith('/notifications')) {
        deleteCollectionCalls += 1
      }
    })

    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()

    await bell.clickClearAll()

    await expect(bell.confirmRow).toBeVisible()
    await expect(bell.confirmRow).toContainText('Sure?')
    await expect(bell.confirmYes).toBeVisible()
    await expect(bell.confirmNo).toBeVisible()
    // .danger-action button is hidden by v-if/v-else when confirm row shows
    await expect(bell.clearAllButton).toHaveCount(0)
    expect(deleteCollectionCalls).toBe(0)
  })

  // ─── TC-028 ──────────────────────────────────────────────────────────────
  test('TC-028: clicking "No" in confirm row restores the "Clear all" button', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(1) })
    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()
    await bell.clickClearAll()
    await expect(bell.confirmRow).toBeVisible()

    await bell.cancelClearAll()

    await expect(bell.confirmRow).toHaveCount(0)
    await expect(bell.clearAllButton).toBeVisible()
  })

  // ─── TC-029 ──────────────────────────────────────────────────────────────
  test('TC-029: clicking "Yes" clears all notifications and closes panel', async ({ page }) => {
    await setupNotificationRoutes(page, { items: buildUnread(2) })
    const bell = new NotificationBellPage(page)
    await bell.goto()
    await bell.openPanel()
    await bell.clickClearAll()
    await expect(bell.confirmRow).toBeVisible()

    await bell.confirmClearAll()

    await expect(bell.panel).toHaveCount(0)
  })

  // ─── TC-032 ──────────────────────────────────────────────────────────────
  test('TC-032: error snackbar appears when GET /notifications fails', async ({ page }) => {
    await setupNotificationRoutes(page, { getStatus: 500 })
    const bell = new NotificationBellPage(page)
    await bell.goto()

    await expect(bell.snackbar).toBeVisible()
    await expect(bell.snackbar).toContainText('Failed to load notifications')
  })

  // ─── TC-045 ──────────────────────────────────────────────────────────────
  test('TC-045: error snackbar has role=alert and aria-live=assertive', async ({ page }) => {
    await setupNotificationRoutes(page, { getStatus: 500 })
    const bell = new NotificationBellPage(page)
    await bell.goto()

    await expect(bell.snackbar).toBeVisible()
    await expect(bell.snackbar).toHaveAttribute('role', 'alert')
    await expect(bell.snackbar).toHaveAttribute('aria-live', 'assertive')
  })
})
