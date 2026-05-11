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
 * CafeteriaUI — DOM overlay for the cafeteria interior. Mirrors CoffeeBarUI
 * with meal options. Kept visually distinct from the coffee bar header so
 * the player can tell which interior they're inside.
 */

/** Meals shown in the menu. Keep in sync with multiplayer/src/sim/CafeteriaMenu.ts. */
const MENU_MEALS: ReadonlyArray<{ id: string; label: string; emoji: string }> = [
  { id: 'sandwich', label: 'Sandwich', emoji: '\u{1F96A}' },
  { id: 'salad',    label: 'Salad',    emoji: '\u{1F957}' },
  { id: 'curry',    label: 'Curry',    emoji: '\u{1F35B}' },
  { id: 'pizza',    label: 'Pizza',    emoji: '\u{1F355}' },
  { id: 'ramen',    label: 'Ramen',    emoji: '\u{1F35C}' },
]

export class CafeteriaUI {
  private container: HTMLElement | null = null
  private prompt: HTMLElement | null = null
  private exitBtn: HTMLElement | null = null
  private menu: HTMLElement | null = null

  onExitClick: (() => void) | null = null
  onMealSelect: ((mealId: string) => void) | null = null
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

    // Header — sage/leaf palette to read as "canteen / lunchroom" rather
    // than "coffee shop".
    this.makeLabel('\u{1F374} CAFETERIA', {
      position: 'absolute', top: '16px', left: '50%',
      transform: 'translateX(-50%)',
      background: 'rgba(225, 235, 200, 0.92)', color: '#2d4019',
      padding: '5px 18px', borderRadius: '14px',
      fontSize: '13px', letterSpacing: '2px', fontWeight: '700',
      border: '1px solid rgba(60, 100, 30, 0.35)',
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

    this.exitBtn = this.makeLabel('Leave Cafeteria', {
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
    this.onMealSelect = null
    this.onMenuCancel = null
  }

  private buildMenu(): HTMLElement {
    const panel = document.createElement('div')
    Object.assign(panel.style, {
      position: 'absolute', top: '50%', left: '50%',
      transform: 'translate(-50%, -50%)',
      background: 'rgba(24,32,18,0.92)',
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
    title.textContent = 'Pick your meal'
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

    for (const meal of MENU_MEALS) {
      const btn = document.createElement('button')
      btn.textContent = `${meal.emoji}  ${meal.label}`
      Object.assign(btn.style, {
        background: 'rgba(60,100,40,0.85)', color: '#fff',
        border: '1px solid rgba(255,255,255,0.2)',
        padding: '10px 12px', borderRadius: '8px',
        fontSize: '13px', fontWeight: '500',
        cursor: 'pointer',
        transition: 'background 0.15s',
      })
      btn.addEventListener('mouseenter', () => {
        btn.style.background = 'rgba(90,140,55,1)'
      })
      btn.addEventListener('mouseleave', () => {
        btn.style.background = 'rgba(60,100,40,0.85)'
      })
      btn.addEventListener('click', () => {
        this.hideMenu()
        this.onMealSelect?.(meal.id)
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
