import { type Page, type Locator } from '@playwright/test'

export class NotificationBellPage {
  readonly page: Page

  readonly bellButton: Locator
  readonly bellSvg: Locator
  readonly badge: Locator

  readonly panel: Locator
  readonly backdrop: Locator
  readonly markAllReadButton: Locator
  readonly clearAllButton: Locator
  readonly confirmRow: Locator
  readonly confirmYes: Locator
  readonly confirmNo: Locator

  readonly items: Locator
  readonly unreadItems: Locator
  readonly markReadButtons: Locator
  readonly dismissButtons: Locator

  readonly snackbar: Locator

  constructor(page: Page) {
    this.page = page

    this.bellButton = page.locator('.bell-btn')
    this.bellSvg = page.locator('.bell-btn > svg')
    this.badge = page.locator('.bell-btn .badge')

    this.panel = page.locator('.notif-panel')
    this.backdrop = page.locator('.overlay-backdrop')
    this.markAllReadButton = this.panel.getByRole('button', { name: 'Mark all read' })
    // Use .danger-action class, NOT getByRole name — "Clear all" substring
    // also matches the confirm row's "Yes, clear all notifications" aria-label.
    this.clearAllButton = page.locator('button.danger-action')
    this.confirmRow = page.locator('.confirm-row')
    this.confirmYes = this.confirmRow.locator('.confirm-yes')
    this.confirmNo = this.confirmRow.locator('.confirm-no')

    this.items = page.locator('.notif-item')
    this.unreadItems = page.locator('.notif-item.unread')
    this.markReadButtons = page.locator('.action-btn.mark-read')
    this.dismissButtons = page.locator('.action-btn.dismiss')

    this.snackbar = page.locator('.snackbar')
  }

  async goto(path = '/tasks'): Promise<void> {
    await this.page.goto(path)
  }

  async openPanel(): Promise<void> {
    await this.bellButton.click()
  }

  /** Close by clicking the bell again. Uses `force: true` because the
   *  `.overlay-backdrop` (z-index 999) covers the bell when the panel is open. */
  async closePanelByBell(): Promise<void> {
    await this.bellButton.click({ force: true })
  }

  async closePanelByEscape(): Promise<void> {
    await this.page.keyboard.press('Escape')
  }

  async closePanelByBackdrop(): Promise<void> {
    await this.backdrop.click()
  }

  async markItemRead(index = 0): Promise<void> {
    const item = this.items.nth(index)
    await item.hover()
    await item.locator('.action-btn.mark-read').click()
  }

  async dismissItem(index = 0): Promise<void> {
    const item = this.items.nth(index)
    await item.hover()
    await item.locator('.action-btn.dismiss').click()
  }

  async clickClearAll(): Promise<void> {
    await this.clearAllButton.click()
  }

  async confirmClearAll(): Promise<void> {
    await this.confirmYes.click()
  }

  async cancelClearAll(): Promise<void> {
    await this.confirmNo.click()
  }
}
