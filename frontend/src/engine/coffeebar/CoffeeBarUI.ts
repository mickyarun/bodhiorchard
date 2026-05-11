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
 * CoffeeBarUI — DOM overlay for the coffee bar interior.
 *
 * Phase 3 scope: header, controls hint, exit button. Proximity prompt and
 * drink menu slot in here in Phase 4 (see showPrompt / showMenu stubs).
 */

/** Drinks shown in the menu. Keep in sync with multiplayer/src/sim/CoffeeMenu.ts. */
const MENU_DRINKS: ReadonlyArray<{ id: string; label: string; emoji: string }> = [
  { id: 'espresso',   label: 'Espresso',   emoji: '\u2615' },
  { id: 'latte',      label: 'Latte',      emoji: '\u{1F95B}' },
  { id: 'cappuccino', label: 'Cappuccino', emoji: '\u{1F3C6}' },
  { id: 'tea',        label: 'Tea',        emoji: '\u{1F375}' },
]

export class CoffeeBarUI {
  private container: HTMLElement | null = null
  private prompt: HTMLElement | null = null
  private exitBtn: HTMLElement | null = null
  private menu: HTMLElement | null = null

  /** Called when the exit button is clicked. Wired by CoffeeBarManager. */
  onExitClick: (() => void) | null = null

  /** Called when a drink button is clicked. Wired by CoffeeBarManager. */
  onDrinkSelect: ((drinkId: string) => void) | null = null

  /** Called when the menu is dismissed via the cancel button. */
  onMenuCancel: (() => void) | null = null

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

    // Header colours sampled from the Gemini café reference — cream pill with
    // warm espresso-brown text reads as "café signage" rather than "dark chip".
    this.makeLabel('\u2615 COFFEE BAR', {
      position: 'absolute', top: '16px', left: '50%',
      transform: 'translateX(-50%)',
      background: 'rgba(245, 230, 200, 0.92)', color: '#4a2f1a',
      padding: '5px 18px', borderRadius: '14px',
      fontSize: '13px', letterSpacing: '2px', fontWeight: '700',
      border: '1px solid rgba(101, 67, 33, 0.35)',
    })

    this.makeLabel('WASD \u2014 Move   E \u2014 Order   ESC \u2014 Exit', {
      position: 'absolute', bottom: '20px', left: '50%',
      transform: 'translateX(-50%)',
      background: 'rgba(0,0,0,0.45)', color: 'rgba(255,255,255,0.75)',
      padding: '6px 18px', borderRadius: '20px',
      fontSize: '12px', letterSpacing: '1px',
    })

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

    this.exitBtn = this.makeLabel('Leave Coffee Bar', {
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

  show(): void {
    if (this.container) this.container.style.display = 'block'
  }

  hide(): void {
    if (this.container) this.container.style.display = 'none'
    this.hidePrompt()
    this.hideMenu()
  }

  showPrompt(text: string): void {
    if (!this.prompt) return
    this.prompt.textContent = text
    this.prompt.style.display = 'block'
  }

  hidePrompt(): void {
    if (this.prompt) this.prompt.style.display = 'none'
  }

  /**
   * Show the drink-selection menu. Lazily built on first call so the DOM
   * cost is only paid by players who actually order a drink.
   */
  showMenu(): void {
    if (!this.container) return
    if (!this.menu) this.menu = this.buildMenu()
    this.menu.style.display = 'flex'
    this.hidePrompt()
  }

  hideMenu(): void {
    if (this.menu) this.menu.style.display = 'none'
  }

  destroy(): void {
    this.container?.remove()
    this.container = null
    this.prompt = null
    this.exitBtn = null
    this.menu = null
    this.onExitClick = null
    this.onDrinkSelect = null
    this.onMenuCancel = null
  }

  private buildMenu(): HTMLElement {
    const panel = document.createElement('div')
    Object.assign(panel.style, {
      position: 'absolute', top: '50%', left: '50%',
      transform: 'translate(-50%, -50%)',
      background: 'rgba(30,24,18,0.92)',
      backdropFilter: 'blur(8px)',
      padding: '20px 22px',
      borderRadius: '14px',
      border: '1px solid rgba(255,255,255,0.18)',
      display: 'none',
      flexDirection: 'column',
      gap: '12px',
      pointerEvents: 'auto',
      minWidth: '260px',
    })

    const title = document.createElement('div')
    title.textContent = 'Pick your drink'
    Object.assign(title.style, {
      color: '#fff', fontSize: '14px', fontWeight: '600',
      textAlign: 'center', letterSpacing: '1px',
    })
    panel.appendChild(title)

    const grid = document.createElement('div')
    Object.assign(grid.style, {
      display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px',
    })
    panel.appendChild(grid)

    for (const drink of MENU_DRINKS) {
      const btn = document.createElement('button')
      btn.textContent = `${drink.emoji}  ${drink.label}`
      Object.assign(btn.style, {
        background: 'rgba(101,67,33,0.85)', color: '#fff',
        border: '1px solid rgba(255,255,255,0.2)',
        padding: '10px 12px', borderRadius: '8px',
        fontSize: '13px', fontWeight: '500',
        cursor: 'pointer',
        transition: 'background 0.15s',
      })
      btn.addEventListener('mouseenter', () => {
        btn.style.background = 'rgba(140,95,55,1)'
      })
      btn.addEventListener('mouseleave', () => {
        btn.style.background = 'rgba(101,67,33,0.85)'
      })
      btn.addEventListener('click', () => {
        this.hideMenu()
        this.onDrinkSelect?.(drink.id)
      })
      grid.appendChild(btn)
    }

    const cancel = document.createElement('button')
    cancel.textContent = 'Cancel'
    Object.assign(cancel.style, {
      background: 'transparent', color: 'rgba(255,255,255,0.7)',
      border: '1px solid rgba(255,255,255,0.3)',
      padding: '8px 12px', borderRadius: '8px',
      fontSize: '12px', cursor: 'pointer',
    })
    cancel.addEventListener('click', () => {
      this.hideMenu()
      this.onMenuCancel?.()
    })
    panel.appendChild(cancel)

    this.container!.appendChild(panel)
    return panel
  }

  private makeLabel(text: string, styles: Partial<CSSStyleDeclaration>): HTMLElement {
    const el = document.createElement('div')
    el.textContent = text
    Object.assign(el.style, styles)
    this.container!.appendChild(el)
    return el
  }
}
