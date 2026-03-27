/**
 * HouseTestUI — HTML overlay for the house demo.
 *
 * Shows WASD controls hint, current scene label, and proximity
 * interaction prompts. Pure DOM — no PlayCanvas dependency.
 */
export class HouseTestUI {
  private container: HTMLElement | null = null
  private sceneLabel: HTMLElement | null = null
  private prompt: HTMLElement | null = null
  private infoText: HTMLElement | null = null
  private promptTimeout: ReturnType<typeof setTimeout> | null = null

  init(parent: HTMLElement): void {
    this.container = document.createElement('div')
    Object.assign(this.container.style, {
      position: 'absolute',
      inset: '0',
      pointerEvents: 'none',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      userSelect: 'none',
    })
    parent.style.position = 'relative'
    parent.appendChild(this.container)

    this.sceneLabel = this.makeLabel('EXTERIOR', {
      position: 'absolute', top: '16px', left: '50%',
      transform: 'translateX(-50%)',
      background: 'rgba(0,0,0,0.5)', color: '#fff',
      padding: '4px 14px', borderRadius: '12px',
      fontSize: '13px', letterSpacing: '2px', fontWeight: '600',
    })

    this.makeLabel('WASD — Move   E — Interact   Drag — Orbit   Scroll — Zoom', {
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

    this.infoText = this.makeLabel('', {
      position: 'absolute', top: '42%', left: '50%',
      transform: 'translate(-50%, -50%)',
      background: 'rgba(40,40,40,0.8)', color: '#fff',
      padding: '10px 24px', borderRadius: '16px',
      fontSize: '15px', fontWeight: '500',
      display: 'none',
    })
  }

  setScene(scene: 'exterior' | 'interior'): void {
    if (this.sceneLabel) {
      this.sceneLabel.textContent = scene === 'exterior' ? 'EXTERIOR' : 'INTERIOR'
    }
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
    if (this.promptTimeout) clearTimeout(this.promptTimeout)
    this.promptTimeout = setTimeout(() => {
      if (this.infoText) this.infoText.style.display = 'none'
    }, 2000)
  }

  destroy(): void {
    if (this.promptTimeout) clearTimeout(this.promptTimeout)
    this.container?.remove()
    this.container = null
    this.sceneLabel = null
    this.prompt = null
    this.infoText = null
  }

  private makeLabel(text: string, styles: Partial<CSSStyleDeclaration>): HTMLElement {
    const el = document.createElement('div')
    el.textContent = text
    Object.assign(el.style, styles)
    this.container!.appendChild(el)
    return el
  }
}
