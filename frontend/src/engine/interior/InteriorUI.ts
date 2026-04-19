// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * InteriorUI — HTML overlay for the interior exploration mode.
 *
 * Adapted from housetest/HouseTestUI with:
 *   - Member name header (whose house you're in)
 *   - Exit button with callback
 *   - Interaction prompts + info text
 *   - Controls hint
 *
 * Pure DOM — no PlayCanvas dependency. All elements use pointerEvents: 'none'
 * except the exit button which must be clickable.
 */

export class InteriorUI {
  private container: HTMLElement | null = null
  private header: HTMLElement | null = null
  private prompt: HTMLElement | null = null
  private infoText: HTMLElement | null = null
  private exitBtn: HTMLElement | null = null
  private infoTimeout: ReturnType<typeof setTimeout> | null = null

  /** Called when exit button is clicked. Set by InteriorManager. */
  onExitClick: (() => void) | null = null

  init(parent: HTMLElement): void {
    this.container = document.createElement('div')
    Object.assign(this.container.style, {
      position: 'absolute', inset: '0',
      pointerEvents: 'none',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      userSelect: 'none',
    })
    parent.style.position = 'relative'
    parent.appendChild(this.container)

    // Member name header
    this.header = this.makeLabel('', {
      position: 'absolute', top: '16px', left: '50%',
      transform: 'translateX(-50%)',
      background: 'rgba(0,0,0,0.5)', color: '#fff',
      padding: '4px 14px', borderRadius: '12px',
      fontSize: '13px', letterSpacing: '2px', fontWeight: '600',
    })

    // Controls hint
    this.makeLabel('WASD \u2014 Move   E \u2014 Interact   Drag \u2014 Orbit   Scroll \u2014 Zoom   ESC \u2014 Exit', {
      position: 'absolute', bottom: '20px', left: '50%',
      transform: 'translateX(-50%)',
      background: 'rgba(0,0,0,0.45)', color: 'rgba(255,255,255,0.75)',
      padding: '6px 18px', borderRadius: '20px',
      fontSize: '12px', letterSpacing: '1px',
    })

    // Interaction prompt
    this.prompt = this.makeLabel('', {
      position: 'absolute', top: '55%', left: '50%',
      transform: 'translate(-50%, -50%)',
      background: 'rgba(255,255,255,0.15)',
      backdropFilter: 'blur(4px)',
      color: '#fff', padding: '8px 20px', borderRadius: '16px',
      fontSize: '14px', fontWeight: '500',
      border: '1px solid rgba(255,255,255,0.25)',
      display: 'none', transition: 'opacity 0.2s',
    })

    // Info text (auto-hides after 2s)
    this.infoText = this.makeLabel('', {
      position: 'absolute', top: '42%', left: '50%',
      transform: 'translate(-50%, -50%)',
      background: 'rgba(40,40,40,0.8)', color: '#fff',
      padding: '10px 24px', borderRadius: '16px',
      fontSize: '15px', fontWeight: '500',
      display: 'none',
    })

    // Exit button — must be clickable
    this.exitBtn = this.makeLabel('Exit House', {
      position: 'absolute', top: '16px', right: '16px',
      background: 'rgba(220,60,60,0.8)', color: '#fff',
      padding: '6px 16px', borderRadius: '8px',
      fontSize: '13px', fontWeight: '600', cursor: 'pointer',
      pointerEvents: 'auto',
      border: '1px solid rgba(255,255,255,0.3)',
      transition: 'background 0.2s',
    })
    this.exitBtn.addEventListener('mouseenter', () => {
      if (this.exitBtn) this.exitBtn.style.background = 'rgba(220,60,60,1)'
    })
    this.exitBtn.addEventListener('mouseleave', () => {
      if (this.exitBtn) this.exitBtn.style.background = 'rgba(220,60,60,0.8)'
    })
    this.exitBtn.addEventListener('click', () => this.onExitClick?.())
  }

  /** Show UI with member name. */
  show(memberName: string): void {
    if (!this.container) return
    this.container.style.display = 'block'
    if (this.header) this.header.textContent = `${memberName}'s House`.toUpperCase()
  }

  hide(): void {
    if (!this.container) return
    this.container.style.display = 'none'
    this.hidePrompt()
  }

  showPrompt(text: string): void {
    if (!this.prompt) return
    this.prompt.textContent = text
    this.prompt.style.display = 'block'
  }

  hidePrompt(): void {
    if (this.prompt) this.prompt.style.display = 'none'
  }

  showInfo(text: string): void {
    if (!this.infoText) return
    this.infoText.textContent = text
    this.infoText.style.display = 'block'
    if (this.infoTimeout) clearTimeout(this.infoTimeout)
    this.infoTimeout = setTimeout(() => {
      if (this.infoText) this.infoText.style.display = 'none'
    }, 2000)
  }

  destroy(): void {
    if (this.infoTimeout) clearTimeout(this.infoTimeout)
    this.container?.remove()
    this.container = null
    this.header = null
    this.prompt = null
    this.infoText = null
    this.exitBtn = null
    this.onExitClick = null
  }

  private makeLabel(text: string, styles: Partial<CSSStyleDeclaration>): HTMLElement {
    const el = document.createElement('div')
    el.textContent = text
    Object.assign(el.style, styles)
    this.container!.appendChild(el)
    return el
  }
}
