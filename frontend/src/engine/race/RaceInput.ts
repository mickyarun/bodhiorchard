// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * RaceInput — keyboard listener for the race module.
 *
 * Supports two kinds of bindings:
 *   - TAP bindings: one-shot callback on key press (for boost keys, join
 *     presses, etc.). Filters OS auto-repeat so holding a key doesn't spam.
 *   - HOLD bindings: queryable down/up state (for run keys). The consumer
 *     polls `isDown(keyCode)` each frame.
 *
 * A single native `keydown` + `keyup` listener covers all bindings —
 * preventDefault() is applied so SPACE/UP-ARROW don't scroll the page or
 * activate focused UI elements.
 */

interface TapBinding {
  onTap: () => void
}

export class RaceInput {
  private keydownHandler: ((e: KeyboardEvent) => void) | null = null
  private keyupHandler: ((e: KeyboardEvent) => void) | null = null
  private tapBindings = new Map<string, TapBinding>()
  private holdKeys = new Set<string>()
  private downKeys = new Set<string>()
  private enabled = false

  /**
   * Register a tap callback. Fires once per physical press (auto-repeat
   * events ignored). Last registration wins if the same code is bound twice.
   */
  bindTap(keyCode: string, onTap: () => void): void {
    this.tapBindings.set(keyCode, { onTap })
  }

  /**
   * Register a hold key. Does not fire callbacks — consumers poll
   * `isDown(keyCode)` each tick to read the current press state.
   */
  bindHold(keyCode: string): void {
    this.holdKeys.add(keyCode)
  }

  /** Query whether a registered hold key is currently pressed. */
  isDown(keyCode: string): boolean {
    if (!this.enabled) return false
    return this.downKeys.has(keyCode)
  }

  /** Install the window listeners. Call once after binding. */
  start(): void {
    this.keydownHandler = (e: KeyboardEvent) => {
      const isTap = this.tapBindings.has(e.code)
      const isHold = this.holdKeys.has(e.code)
      if (!isTap && !isHold) return
      // Only block browser defaults while we're actually consuming the
      // key. When disabled (e.g. during countdown / finished phases),
      // let the default behaviour through so the user can still tab away,
      // focus form fields, etc.
      if (!this.enabled) return
      e.preventDefault()

      if (isHold) this.downKeys.add(e.code)
      if (isTap && !e.repeat) {
        const binding = this.tapBindings.get(e.code)
        if (binding) binding.onTap()
      }
    }
    this.keyupHandler = (e: KeyboardEvent) => {
      if (!this.holdKeys.has(e.code)) return
      // Mirror the keydown guard — only preventDefault when we're live.
      if (this.enabled) e.preventDefault()
      this.downKeys.delete(e.code)
    }
    window.addEventListener('keydown', this.keydownHandler)
    window.addEventListener('keyup', this.keyupHandler)
  }

  /** Enable / disable tap acceptance + isDown responses. Listeners stay installed. */
  setEnabled(enabled: boolean): void {
    this.enabled = enabled
    if (!enabled) this.downKeys.clear()
  }

  destroy(): void {
    if (this.keydownHandler) window.removeEventListener('keydown', this.keydownHandler)
    if (this.keyupHandler) window.removeEventListener('keyup', this.keyupHandler)
    this.keydownHandler = null
    this.keyupHandler = null
    this.tapBindings.clear()
    this.holdKeys.clear()
    this.downKeys.clear()
    this.enabled = false
  }
}
