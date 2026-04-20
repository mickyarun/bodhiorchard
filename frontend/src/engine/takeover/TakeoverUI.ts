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
   * Invoked when the user clicks "Invite to race" on the member action
   * panel. `userId` is the targeted member. Wired by GardenEngine to
   * bubble up to the Vue layer (which opens `<RaceSetupDialog>`).
   *
   * Greet is hotkey-only (`3`) — no button callback. The once-per-target
   * SP rule made a second button click look broken, so Greet lives on
   * the keyboard where the wave animation always plays on every press.
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

    // Controls hint (bottom center). The 3/4 hotkeys are contextual
    // (only act when near another player); we still show them here so
    // players learn the binding the first time they stand next to
    // someone, without needing to read the proximity panel closely.
    this.makeLabel(
      'WASD \u2014 Move   Shift \u2014 Sprint   Space \u2014 Jump   Drag \u2014 Orbit   ESC \u2014 Exit   1 \u2014 Wave   2 \u2014 Cheer   3 \u2014 Greet   4 \u2014 Invite',
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
   * Show an action panel next to the nearby member. One chip: Invite
   * to race (`onInviteNearbyToRace`, hotkey `4`). Greet is hotkey-only
   * (`3`) — a small keycap hint next to the target name advertises
   * the binding. The button was removed because the once-per-target SP
   * rule made second-click look broken, and a button that silently
   * no-ops on the second click is worse than no button at all.
   */
  showMemberActionPanel(userId: string, name: string): void {
    if (!this.container) return
    if (this.actionPanelUserId === userId && this.actionPanel) {
      const label = this.actionPanel.querySelector<HTMLElement>('[data-label]')
      if (label) label.textContent = name
      const avatar = this.actionPanel.querySelector<HTMLElement>('[data-avatar]')
      if (avatar) avatar.textContent = initialsFor(name)
      return
    }

    this.hideMemberActionPanel()
    ensurePanelStyles()

    const panel = document.createElement('div')
    panel.className = 'to-actpanel'

    const target = document.createElement('div')
    target.className = 'to-actpanel__target'

    const avatar = document.createElement('div')
    avatar.className = 'to-actpanel__avatar'
    avatar.dataset.avatar = ''
    avatar.textContent = initialsFor(name)

    const nameEl = document.createElement('div')
    nameEl.className = 'to-actpanel__name'
    nameEl.dataset.label = ''
    nameEl.textContent = name

    target.appendChild(avatar)
    target.appendChild(nameEl)

    // Keycap hint for the keyboard-only Greet action. Uses the same
    // keycap styling as the action chip so players learn "3 waves at
    // them" without a dedicated (and failure-prone) button.
    const greetHint = document.createElement('div')
    greetHint.className = 'to-actpanel__hint'
    const greetKey = document.createElement('span')
    greetKey.className = 'to-actpanel__hintkey'
    greetKey.textContent = '3'
    const greetLabel = document.createElement('span')
    greetLabel.textContent = '\ud83d\udc4b Greet'
    greetHint.appendChild(greetKey)
    greetHint.appendChild(greetLabel)

    const divider = document.createElement('div')
    divider.className = 'to-actpanel__divider'

    const raceChip = makeActionChip({
      keyLabel: '4',
      icon: '\ud83c\udfc1',
      text: 'Invite to race',
      variant: 'primary',
      onClick: () => this.onInviteNearbyToRace?.(userId, name),
    })

    panel.appendChild(target)
    panel.appendChild(greetHint)
    panel.appendChild(divider)
    panel.appendChild(raceChip)

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

interface ActionChipOpts {
  keyLabel: string
  icon: string
  text: string
  variant: 'neutral' | 'primary'
  onClick: () => void
}

/**
 * A button styled as `[key] icon label`. The keycap is a small bevelled
 * square mirroring the hardware key so the hotkey binding is legible
 * at a glance. `variant` picks a palette: `primary` tints the chip
 * with the race accent to signal the headline action.
 */
function makeActionChip(opts: ActionChipOpts): HTMLButtonElement {
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.className = `to-actchip to-actchip--${opts.variant}`

  const key = document.createElement('span')
  key.className = 'to-actchip__key'
  key.textContent = opts.keyLabel

  const icon = document.createElement('span')
  icon.className = 'to-actchip__icon'
  icon.textContent = opts.icon

  const label = document.createElement('span')
  label.className = 'to-actchip__label'
  label.textContent = opts.text

  btn.appendChild(key)
  btn.appendChild(icon)
  btn.appendChild(label)

  btn.addEventListener('click', opts.onClick)
  return btn
}

/**
 * Pull initials out of a display name for the target avatar chip.
 * Inline rather than importing from `components/race/initials` so the
 * engine layer stays independent of the Vue-layer helpers.
 */
function initialsFor(name: string): string {
  if (!name) return '?'
  const cleaned = name.replace(/…$/, '').trim()
  if (!cleaned) return '?'
  const parts = cleaned.split(/\s+/)
  const first = parts[0][0] ?? ''
  const last = parts.length > 1 ? parts[parts.length - 1][0] ?? '' : ''
  return (first + last).toUpperCase() || '?'
}

let panelStylesInjected = false
/**
 * Inject the proximity panel + action chip CSS once per page. Using a
 * stylesheet (rather than inline style= on every element) lets us
 * express :hover, :active, and keyframes cleanly — hover glows and
 * the entrance animation would be awkward to wire via JS listeners.
 */
function ensurePanelStyles(): void {
  if (panelStylesInjected) return
  panelStylesInjected = true
  const style = document.createElement('style')
  style.id = 'takeover-actpanel-css'
  style.textContent = `
    .to-actpanel {
      position: absolute;
      bottom: 120px;
      left: 50%;
      transform: translateX(-50%);
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px 8px 12px;
      background: linear-gradient(180deg, rgba(22,28,44,0.82) 0%, rgba(14,18,32,0.88) 100%);
      color: #fff;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.12);
      box-shadow:
        0 10px 30px rgba(0,0,0,0.35),
        inset 0 1px 0 rgba(255,255,255,0.08);
      backdrop-filter: blur(10px) saturate(140%);
      -webkit-backdrop-filter: blur(10px) saturate(140%);
      font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
      pointer-events: auto;
      animation: to-actpanel-in 180ms cubic-bezier(0.22, 1, 0.36, 1);
    }

    .to-actpanel__target {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 2px 4px 2px 2px;
    }

    .to-actpanel__avatar {
      width: 26px;
      height: 26px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.4px;
      color: #fff;
      background: linear-gradient(135deg, #5865F2 0%, #8B5CF6 100%);
      box-shadow: inset 0 1px 0 rgba(255,255,255,0.25), 0 1px 2px rgba(0,0,0,0.25);
      flex-shrink: 0;
    }

    .to-actpanel__name {
      font-size: 13px;
      font-weight: 600;
      letter-spacing: 0.2px;
      color: rgba(255,255,255,0.95);
      max-width: 140px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .to-actpanel__divider {
      width: 1px;
      align-self: stretch;
      margin: 4px 2px;
      background: rgba(255,255,255,0.12);
    }

    .to-actpanel__hint {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 500;
      color: rgba(255,255,255,0.7);
      letter-spacing: 0.2px;
      padding: 4px 6px;
      user-select: none;
      -webkit-user-select: none;
    }

    .to-actpanel__hintkey {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 18px;
      height: 18px;
      padding: 0 4px;
      border-radius: 5px;
      font-size: 10px;
      font-weight: 800;
      color: rgba(255,255,255,0.9);
      background: linear-gradient(180deg, rgba(255,255,255,0.15) 0%, rgba(255,255,255,0.06) 100%);
      border: 1px solid rgba(255,255,255,0.22);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.25),
        0 1px 0 rgba(0,0,0,0.2);
    }

    .to-actchip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 12px 6px 6px;
      border-radius: 10px;
      border: 1px solid transparent;
      cursor: pointer;
      font-family: inherit;
      font-size: 13px;
      font-weight: 600;
      line-height: 1;
      color: #fff;
      /* Defend against inherited pointer-events:none from the overlay
         container and lift above any sibling with a lurking higher
         stacking order created by backdrop-filter. */
      pointer-events: auto;
      position: relative;
      z-index: 1;
      user-select: none;
      -webkit-user-select: none;
      transition: transform 120ms ease, background 120ms ease, border-color 120ms ease, box-shadow 120ms ease;
    }

    /* Children are decorative — clicking the keycap, emoji, or label
       must resolve as a click on the button itself. Without this, the
       browser can treat the span as the event target and the button's
       click listener never fires (most reproducible on Safari and
       inside backdrop-filter stacking contexts). */
    .to-actchip > * {
      pointer-events: none;
    }

    .to-actchip__key {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 22px;
      height: 22px;
      padding: 0 6px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.5px;
      color: rgba(255,255,255,0.95);
      background: linear-gradient(180deg, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.08) 100%);
      border: 1px solid rgba(255,255,255,0.28);
      box-shadow:
        inset 0 1px 0 rgba(255,255,255,0.3),
        inset 0 -1px 0 rgba(0,0,0,0.15),
        0 1px 0 rgba(0,0,0,0.25);
      text-shadow: 0 1px 0 rgba(0,0,0,0.25);
    }

    .to-actchip__icon {
      font-size: 15px;
      line-height: 1;
    }

    .to-actchip__label {
      letter-spacing: 0.3px;
    }

    .to-actchip--neutral {
      background: rgba(255,255,255,0.08);
      border-color: rgba(255,255,255,0.14);
    }
    .to-actchip--neutral:hover {
      background: rgba(255,255,255,0.14);
      border-color: rgba(255,255,255,0.24);
      transform: translateY(-1px);
    }
    .to-actchip--neutral:active {
      transform: translateY(0);
      background: rgba(255,255,255,0.22);
    }

    .to-actchip--primary {
      background: linear-gradient(180deg, rgba(210,34,34,0.95) 0%, rgba(170,22,22,0.95) 100%);
      border-color: rgba(255,180,180,0.35);
      box-shadow: 0 4px 14px rgba(210,34,34,0.35);
    }
    .to-actchip--primary:hover {
      background: linear-gradient(180deg, rgba(230,48,48,1) 0%, rgba(195,30,30,1) 100%);
      border-color: rgba(255,200,200,0.5);
      transform: translateY(-1px);
      box-shadow: 0 6px 18px rgba(210,34,34,0.45);
    }
    .to-actchip--primary:active {
      transform: translateY(0);
    }

    @keyframes to-actpanel-in {
      from { opacity: 0; transform: translateX(-50%) translateY(6px) scale(0.96); }
      to   { opacity: 1; transform: translateX(-50%) translateY(0)   scale(1);    }
    }
  `
  document.head.appendChild(style)
}
