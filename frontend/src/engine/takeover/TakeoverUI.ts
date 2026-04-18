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
  private memberCard: HTMLElement | null = null
  private warning: HTMLElement | null = null
  private seatPrompt: HTMLElement | null = null
  private exitBtn: HTMLElement | null = null
  private parentEl: HTMLElement | null = null
  private originalParentPosition = ''

  /** Called when exit button is clicked. Set by GardenEngine. */
  onExitClick: (() => void) | null = null

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

    // Proximity member info card (above controls hint)
    this.memberCard = this.makeLabel('', {
      position: 'absolute', bottom: '60px', left: '50%',
      transform: 'translateX(-50%)',
      background: 'rgba(30,60,120,0.8)',
      backdropFilter: 'blur(4px)',
      color: '#fff', padding: '8px 20px', borderRadius: '12px',
      fontSize: '14px', fontWeight: '500',
      border: '1px solid rgba(255,255,255,0.2)',
      display: 'none', transition: 'opacity 0.2s',
    })

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
    this.hideMemberInfo()
    this.hideWarning()
  }

  /** Show proximity member info card. */
  showMemberInfo(name: string, status: string): void {
    if (!this.memberCard) return
    this.memberCard.textContent = `${name} \u2014 ${status}`
    this.memberCard.style.display = 'block'
  }

  hideMemberInfo(): void {
    if (this.memberCard) this.memberCard.style.display = 'none'
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

  destroy(): void {
    if (this.parentEl) {
      this.parentEl.style.position = this.originalParentPosition
      this.parentEl = null
    }
    this.container?.remove()
    this.container = null
    this.memberCard = null
    this.warning = null
    this.seatPrompt = null
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
