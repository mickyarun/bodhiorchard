/**
 * UIOverlay — HTML controls overlay for the tree growth demo.
 *
 * Pure DOM manipulation. Creates a floating panel with:
 * - "Grow" button (disabled during transitions)
 * - "Reset" button
 * - Stage indicator label
 * - Progress bar during transitions
 */
const STAGE_NAMES = ['Seed', 'Growing...', 'Tree'] as const

export class UIOverlay {
  private container: HTMLElement
  private panel!: HTMLElement
  private growBtn!: HTMLButtonElement
  private resetBtn!: HTMLButtonElement
  private stageLabel!: HTMLElement
  private progressBar!: HTMLElement
  private progressFill!: HTMLElement

  private onGrowCallback: (() => void) | null = null
  private onResetCallback: (() => void) | null = null

  constructor(container: HTMLElement) {
    this.container = container
    this.build()
  }

  private build(): void {
    this.container.style.position = 'relative'

    this.panel = document.createElement('div')
    Object.assign(this.panel.style, {
      position: 'absolute',
      bottom: '24px',
      left: '50%',
      transform: 'translateX(-50%)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '10px',
      zIndex: '10',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      pointerEvents: 'none',
    })

    // Stage label
    this.stageLabel = document.createElement('div')
    Object.assign(this.stageLabel.style, {
      background: 'rgba(0, 0, 0, 0.65)',
      color: '#fff',
      fontSize: '14px',
      fontWeight: '600',
      padding: '6px 16px',
      borderRadius: '20px',
      letterSpacing: '0.5px',
      backdropFilter: 'blur(8px)',
    })
    this.stageLabel.textContent = 'Stage 1/6: Seed'

    // Progress bar
    this.progressBar = document.createElement('div')
    Object.assign(this.progressBar.style, {
      width: '200px',
      height: '4px',
      borderRadius: '2px',
      background: 'rgba(255, 255, 255, 0.2)',
      overflow: 'hidden',
      opacity: '0',
      transition: 'opacity 0.3s',
    })
    this.progressFill = document.createElement('div')
    Object.assign(this.progressFill.style, {
      width: '0%',
      height: '100%',
      borderRadius: '2px',
      background: 'linear-gradient(90deg, #4ade80, #22c55e)',
      transition: 'width 0.1s linear',
    })
    this.progressBar.appendChild(this.progressFill)

    // Button row
    const btnRow = document.createElement('div')
    Object.assign(btnRow.style, {
      display: 'flex',
      gap: '10px',
      pointerEvents: 'auto',
    })

    // Grow button
    this.growBtn = document.createElement('button')
    this.growBtn.textContent = 'Grow'
    Object.assign(this.growBtn.style, {
      background: 'linear-gradient(135deg, #22c55e, #16a34a)',
      color: '#fff',
      border: 'none',
      borderRadius: '24px',
      padding: '10px 32px',
      fontSize: '16px',
      fontWeight: '700',
      cursor: 'pointer',
      boxShadow: '0 4px 15px rgba(34, 197, 94, 0.4)',
      transition: 'all 0.2s ease',
      letterSpacing: '0.5px',
    })
    this.growBtn.addEventListener('mouseenter', () => {
      if (!this.growBtn.disabled) {
        this.growBtn.style.transform = 'scale(1.05)'
        this.growBtn.style.boxShadow = '0 6px 20px rgba(34, 197, 94, 0.5)'
      }
    })
    this.growBtn.addEventListener('mouseleave', () => {
      this.growBtn.style.transform = 'scale(1)'
      this.growBtn.style.boxShadow = '0 4px 15px rgba(34, 197, 94, 0.4)'
    })
    this.growBtn.addEventListener('click', () => this.onGrowCallback?.())

    // Reset button
    this.resetBtn = document.createElement('button')
    this.resetBtn.textContent = 'Reset'
    Object.assign(this.resetBtn.style, {
      background: 'rgba(255, 255, 255, 0.15)',
      color: '#fff',
      border: '1px solid rgba(255, 255, 255, 0.3)',
      borderRadius: '24px',
      padding: '10px 20px',
      fontSize: '14px',
      fontWeight: '500',
      cursor: 'pointer',
      backdropFilter: 'blur(8px)',
      transition: 'all 0.2s ease',
    })
    this.resetBtn.addEventListener('mouseenter', () => {
      this.resetBtn.style.background = 'rgba(255, 255, 255, 0.25)'
    })
    this.resetBtn.addEventListener('mouseleave', () => {
      this.resetBtn.style.background = 'rgba(255, 255, 255, 0.15)'
    })
    this.resetBtn.addEventListener('click', () => this.onResetCallback?.())

    btnRow.appendChild(this.growBtn)
    btnRow.appendChild(this.resetBtn)

    this.panel.appendChild(this.stageLabel)
    this.panel.appendChild(this.progressBar)
    this.panel.appendChild(btnRow)
    this.container.appendChild(this.panel)
  }

  onGrow(callback: () => void): void {
    this.onGrowCallback = callback
  }

  onReset(callback: () => void): void {
    this.onResetCallback = callback
  }

  setStage(stageIdx: number): void {
    const name = STAGE_NAMES[stageIdx] ?? 'Tree'
    this.stageLabel.textContent = name
  }

  setGrowEnabled(enabled: boolean): void {
    this.growBtn.disabled = !enabled
    this.growBtn.style.opacity = enabled ? '1' : '0.5'
    this.growBtn.style.cursor = enabled ? 'pointer' : 'not-allowed'
  }

  setGrowLabel(text: string): void {
    this.growBtn.textContent = text
  }

  showProgress(fraction: number): void {
    this.progressBar.style.opacity = fraction > 0 && fraction < 1 ? '1' : '0'
    this.progressFill.style.width = `${Math.round(fraction * 100)}%`
  }

  destroy(): void {
    this.panel.remove()
  }
}
