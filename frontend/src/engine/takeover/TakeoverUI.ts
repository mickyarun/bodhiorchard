// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * TakeoverUI — HTML overlay for garden takeover mode.
 *
 * Provides:
 *   - Controls hint (bottom center)
 *   - Exit button (top right)
 *   - Proximity member info card (bottom center, above controls)
 *   - Inactivity warning (top center)
 *
 * Pure DOM — no PlayCanvas dependency. Same pattern as InteriorUI.
 */

export class TakeoverUI {
  private container: HTMLElement | null = null
  private actionPanel: HTMLElement | null = null
  private actionPanelUserId: string | null = null
  private warning: HTMLElement | null = null
  private seatPrompt: HTMLElement | null = null
  private exitBtn: HTMLElement | null = null
  private parentEl: HTMLElement | null = null
  private originalParentPosition = ''

  /** Called when exit button is clicked. Set by GardenEngine. */
  onExitClick: (() => void) | null = null

  /**
   * Invoked when the user clicks "Greet" on the member action panel.
   * `userId` is the targeted member. Wired by GardenEngine.
   */
  onGreetNearby: ((userId: string, name: string) => void) | null = null

  /**
   * Invoked when the user clicks "Invite to race" on the member action
   * panel. `userId` is the targeted member. Wired by GardenEngine to
   * bubble up to the Vue layer (which opens `<RaceSetupDialog>`).
   */
  onInviteNearbyToRace: ((userId: string, name: string) => void) | null = null

  init(parent: HTMLElement): void {
    this.container = document.createElement('div')
    Object.assign(this.container.style, {
      position: 'absolute', inset: '0',
      pointerEvents: 'none',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      userSelect: 'none',
    })
    this.parentEl = parent
    this.originalParentPosition = parent.style.position
    parent.style.position = 'relative'
    parent.appendChild(this.container)

    // Controls hint (bottom center)
    this.makeLabel(
      'WASD \u2014 Move   Shift \u2014 Sprint   Space \u2014 Jump   Drag \u2014 Orbit   ESC \u2014 Exit   1 \u2014 Wave   2 \u2014 Cheer',
      {
        position: 'absolute', bottom: '20px', left: '50%',
        transform: 'translateX(-50%)',
        background: 'rgba(0,0,0,0.5)', color: 'rgba(255,255,255,0.8)',
        padding: '8px 20px', borderRadius: '20px',
        fontSize: '12px', letterSpacing: '1px',
      },
    )

    // Inactivity warning (top center)
    this.warning = this.makeLabel('', {
      position: 'absolute', top: '60px', left: '50%',
      transform: 'translateX(-50%)',
      background: 'rgba(200,150,0,0.85)', color: '#fff',
      padding: '8px 20px', borderRadius: '12px',
      fontSize: '13px', fontWeight: '600',
      display: 'none',
    })

    // Exit button (top right)
    this.exitBtn = this.makeLabel('Exit', {
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
    if (!this.container) return
    this.container.style.display = 'none'
    this.hideMemberActionPanel()
    this.hideWarning()
  }

  /**
   * Show an action panel next to the nearby member. Two buttons: Greet
   * (fires `onGreetNearby`) and Invite to race (fires `onInviteNearbyToRace`).
   * Idempotent — calling with the same userId is a no-op, so rapid proximity
   * flickers don't rebuild the DOM on every frame.
   */
  showMemberActionPanel(userId: string, name: string): void {
    if (!this.container) return
    if (this.actionPanelUserId === userId && this.actionPanel) {
      // Update label for the same target — in case presence-derived text
      // changed upstream; cheap no-op otherwise.
      const label = this.actionPanel.querySelector<HTMLElement>('[data-label]')
      if (label) label.textContent = name
      return
    }

    this.hideMemberActionPanel()

    const panel = document.createElement('div')
    Object.assign(panel.style, {
      position: 'absolute', bottom: '120px', left: '50%',
      transform: 'translateX(-50%)',
      display: 'flex', gap: '8px', alignItems: 'center',
      background: 'rgba(30,60,120,0.85)',
      backdropFilter: 'blur(4px)',
      color: '#fff', padding: '8px 12px', borderRadius: '12px',
      fontSize: '14px', pointerEvents: 'auto',
      border: '1px solid rgba(255,255,255,0.2)',
    })
    const label = document.createElement('span')
    label.dataset.label = ''
    label.textContent = name
    label.style.marginRight = '4px'
    panel.appendChild(label)

    const greetBtn = makeActionButton('\ud83d\udc4b Greet', () => {
      this.onGreetNearby?.(userId, name)
    })
    const raceBtn = makeActionButton('\ud83c\udfc1 Invite to race', () => {
      this.onInviteNearbyToRace?.(userId, name)
    })
    panel.appendChild(greetBtn)
    panel.appendChild(raceBtn)

    this.container.appendChild(panel)
    this.actionPanel = panel
    this.actionPanelUserId = userId
  }

  hideMemberActionPanel(): void {
    if (this.actionPanel) {
      this.actionPanel.remove()
      this.actionPanel = null
    }
    this.actionPanelUserId = null
  }

  /** Show inactivity warning with countdown. */
  showWarning(secondsLeft: number): void {
    if (!this.warning) return
    this.warning.textContent = `Auto-exit in ${Math.ceil(secondsLeft)}s...`
    this.warning.style.display = 'block'
  }

  hideWarning(): void {
    if (this.warning) this.warning.style.display = 'none'
  }

  /** Show "Press E to sit" prompt when near a chair. */
  showSeatPrompt(): void {
    if (!this.seatPrompt) {
      this.seatPrompt = this.makeLabel(
        '\u24ba Press E to sit',
        {
          position: 'absolute', bottom: '80px', left: '50%',
          transform: 'translateX(-50%)',
          background: 'rgba(0,0,0,0.7)', color: 'rgba(255,255,255,0.8)',
          padding: '6px 14px', borderRadius: '6px',
          fontSize: '13px', pointerEvents: 'none',
        },
      )
    }
    this.seatPrompt.style.display = 'block'
  }

  hideSeatPrompt(): void {
    if (this.seatPrompt) this.seatPrompt.style.display = 'none'
  }

  /**
   * Show a brief confetti + toast celebration for SP rewards.
   * CSS-only confetti — no dependencies.
   */
  showCelebration(message: string): void {
    if (!this.container) return

    // Toast banner
    const toast = document.createElement('div')
    Object.assign(toast.style, {
      position: 'absolute', top: '80px', left: '50%',
      transform: 'translateX(-50%)',
      background: 'linear-gradient(135deg, #D4A843 0%, #F9A825 100%)',
      color: '#1a1a1a', padding: '10px 24px', borderRadius: '8px',
      fontSize: '15px', fontWeight: '700', pointerEvents: 'none',
      zIndex: '10', boxShadow: '0 4px 20px rgba(212, 168, 67, 0.5)',
      animation: 'toast-pop 0.4s ease-out',
    } as Partial<CSSStyleDeclaration>)
    toast.textContent = message
    this.container.appendChild(toast)

    // Confetti particles
    const colors = ['#D4A843', '#F9A825', '#66BB6A', '#42A5F5', '#EF5350', '#AB47BC']
    for (let i = 0; i < 30; i++) {
      const p = document.createElement('div')
      const x = (Math.random() - 0.5) * 300
      const y = -(Math.random() * 200 + 100)
      const rot = Math.random() * 720
      const color = colors[Math.floor(Math.random() * colors.length)]
      const size = 6 + Math.random() * 6
      Object.assign(p.style, {
        position: 'absolute', top: '50%', left: '50%',
        width: size + 'px', height: size + 'px',
        background: color, borderRadius: Math.random() > 0.5 ? '50%' : '2px',
        pointerEvents: 'none', zIndex: '9',
        animation: `confetti-burst 1.2s ease-out forwards`,
        '--cx': x + 'px', '--cy': y + 'px', '--cr': rot + 'deg',
      } as unknown as Partial<CSSStyleDeclaration>)
      this.container.appendChild(p)
      setTimeout(() => p.remove(), 1300)
    }

    // Inject keyframes if not already present
    if (!document.getElementById('takeover-confetti-css')) {
      const style = document.createElement('style')
      style.id = 'takeover-confetti-css'
      style.textContent = `
        @keyframes confetti-burst {
          0% { transform: translate(0, 0) rotate(0deg); opacity: 1; }
          100% { transform: translate(var(--cx), var(--cy)) rotate(var(--cr)); opacity: 0; }
        }
        @keyframes toast-pop {
          0% { transform: translateX(-50%) scale(0.5); opacity: 0; }
          100% { transform: translateX(-50%) scale(1); opacity: 1; }
        }
      `
      document.head.appendChild(style)
    }

    // Auto-remove toast after 3s
    setTimeout(() => toast.remove(), 3000)
  }

  destroy(): void {
    if (this.parentEl) {
      this.parentEl.style.position = this.originalParentPosition
      this.parentEl = null
    }
    this.hideMemberActionPanel()
    this.container?.remove()
    this.container = null
    this.warning = null
    this.seatPrompt = null
    this.exitBtn = null
    this.onExitClick = null
    this.onGreetNearby = null
    this.onInviteNearbyToRace = null
  }

  private makeLabel(text: string, styles: Partial<CSSStyleDeclaration>): HTMLElement {
    const el = document.createElement('div')
    el.textContent = text
    Object.assign(el.style, styles)
    this.container!.appendChild(el)
    return el
  }
}

function makeActionButton(text: string, onClick: () => void): HTMLButtonElement {
  const btn = document.createElement('button')
  btn.textContent = text
  Object.assign(btn.style, {
    background: 'rgba(255,255,255,0.12)',
    color: '#fff',
    padding: '6px 12px', borderRadius: '8px',
    border: '1px solid rgba(255,255,255,0.3)',
    cursor: 'pointer', pointerEvents: 'auto',
    fontSize: '13px', fontWeight: '500',
  })
  btn.addEventListener('mouseenter', () => { btn.style.background = 'rgba(255,255,255,0.22)' })
  btn.addEventListener('mouseleave', () => { btn.style.background = 'rgba(255,255,255,0.12)' })
  btn.addEventListener('click', onClick)
  return btn
}
