/**
 * Notification API mocks for the BUD-001 notification bell test plan.
 *
 * The TaskFlow Web app uses an axios client with `baseURL: http://localhost:9001`
 * and calls `/notifications` (no `/api/v1` prefix). The store fires `fetchAll()`
 * inside `onMounted` on the bell, so any GET interceptor MUST be installed
 * BEFORE `page.goto()` — otherwise the initial fetch slips through unmocked.
 */
import type { Page, Route } from '@playwright/test'

export interface MockNotification {
  id: number
  type: 'task_assigned' | 'task_comment' | 'task_status_changed' | 'invoice_ready' | 'reminder'
  title: string
  body?: string
  time?: string
  is_read: boolean
  is_dismissed?: boolean
}

export function buildUnread(count: number, overrides: Partial<MockNotification> = {}): MockNotification[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    type: 'task_assigned',
    title: `Notification ${i + 1}`,
    body: 'Test notification body',
    time: '2026-04-11T10:00:00Z',
    is_read: false,
    ...overrides,
  }))
}

export function buildRead(count: number, overrides: Partial<MockNotification> = {}): MockNotification[] {
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    type: 'task_assigned',
    title: `Notification ${i + 1}`,
    body: 'Test notification body',
    time: '2026-04-11T10:00:00Z',
    is_read: true,
    ...overrides,
  }))
}

export interface NotificationRouteOptions {
  items?: MockNotification[]
  getStatus?: number
  getDelayMs?: number
  patchReadStatus?: number
  patchReadDelayMs?: number
  postReadAllStatus?: number
  deleteItemStatus?: number
  deleteAllStatus?: number
}

export async function setupNotificationRoutes(
  page: Page,
  opts: NotificationRouteOptions = {},
): Promise<void> {
  const {
    items = [],
    getStatus,
    getDelayMs,
    patchReadStatus = 200,
    patchReadDelayMs,
    postReadAllStatus = 200,
    deleteItemStatus = 200,
    deleteAllStatus = 200,
  } = opts

  // PATCH /notifications/:id/read
  await page.route('**/notifications/*/read', async (route: Route) => {
    if (route.request().method() !== 'PATCH') return route.fallback()
    if (patchReadDelayMs) await new Promise((r) => setTimeout(r, patchReadDelayMs))
    await route.fulfill({ status: patchReadStatus, contentType: 'application/json', body: '{}' })
  })

  // POST /notifications/read-all
  await page.route('**/notifications/read-all', async (route: Route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    await route.fulfill({ status: postReadAllStatus, contentType: 'application/json', body: '{}' })
  })

  // DELETE /notifications/:id (single dismiss)
  await page.route('**/notifications/*', async (route: Route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: deleteItemStatus, contentType: 'application/json', body: '{}' })
      return
    }
    return route.fallback()
  })

  // GET /notifications and DELETE /notifications (clear all)
  await page.route('**/notifications', async (route: Route) => {
    const method = route.request().method()
    if (method === 'GET') {
      if (getDelayMs) await new Promise((r) => setTimeout(r, getDelayMs))
      if (getStatus && getStatus >= 400) {
        await route.fulfill({ status: getStatus, contentType: 'application/json', body: '{"detail":"error"}' })
        return
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(items) })
      return
    }
    if (method === 'DELETE') {
      await route.fulfill({ status: deleteAllStatus, contentType: 'application/json', body: '{}' })
      return
    }
    return route.fallback()
  })
}

export async function seedAuthToken(page: Page, token = 'test-token-bob'): Promise<void> {
  await page.addInitScript((t) => {
    window.localStorage.setItem('access_token', t)
  }, token)
}
