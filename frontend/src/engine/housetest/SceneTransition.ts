/**
 * SceneTransition — fade-to-black overlay for scene swaps.
 *
 * Creates a full-screen HTML div that fades in (black) → swap entities → fades out.
 * The entity toggle happens at the peak opacity so it's invisible to the user.
 */
// Duration must match the CSS transition value below.
const FADE_MS = 350

export class SceneTransition {
  private overlay: HTMLElement | null = null
  private active = false

  init(parent: HTMLElement): void {
    this.overlay = document.createElement('div')
    Object.assign(this.overlay.style, {
      position: 'absolute', inset: '0',
      background: '#000',
      opacity: '0',
      display: 'none',
      transition: `opacity ${FADE_MS / 1000}s ease`,
      zIndex: '100',
      pointerEvents: 'none',
    })
    parent.appendChild(this.overlay)
  }

  get isActive(): boolean { return this.active }

  async perform(onSwap: () => void | Promise<void>): Promise<void> {
    if (this.active || !this.overlay) return
    this.active = true

    // Fade in
    this.overlay.style.display = 'block'
    await this.nextFrame()
    this.overlay.style.opacity = '1'
    await this.wait(FADE_MS)

    // Swap (happens while black — await supports async callbacks like interior build)
    await onSwap()

    // Fade out
    this.overlay.style.opacity = '0'
    await this.wait(FADE_MS)
    this.overlay.style.display = 'none'

    this.active = false
  }

  destroy(): void {
    this.overlay?.remove()
    this.overlay = null
  }

  private wait(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
  }

  private nextFrame(): Promise<void> {
    return new Promise(resolve => requestAnimationFrame(() => resolve()))
  }
}
