/**
 * UIOverlay — HTML controls overlay for the tree growth demo.
 *
 * Pure DOM manipulation. Creates a floating panel with:
 * - Color picker (preset bark colors)
 * - "Grow" / "New Tree" button
 * - "Reset" button
 * - Stage indicator label
 * - Progress bar during transitions
 */
const STAGE_NAMES = ['Seed', 'Growing...', 'Tree'] as const

export type Color3 = [number, number, number]

const COLOR_PRESETS: { label: string; color: Color3; hex: string }[] = [
  { label: 'Cyan',    color: [  0, 180, 200], hex: '#00b4c8' },
  { label: 'Jade',    color: [  0, 200, 120], hex: '#00c878' },
  { label: 'Gold',    color: [220, 160,   0], hex: '#dca000' },
  { label: 'Azure',   color: [ 80, 140, 255], hex: '#508cff' },
  { label: 'Rose',    color: [220,  80, 140], hex: '#dc508c' },
  { label: 'Violet',  color: [160,  80, 255], hex: '#a050ff' },
]

export class UIOverlay {
  private container: HTMLElement
  private panel!: HTMLElement
  private growBtn!: HTMLButtonElement
  private resetBtn!: HTMLButtonElement
  private stageLabel!: HTMLElement
  private progressBar!: HTMLElement
  private progressFill!: HTMLElement
  private colorSelect!: HTMLSelectElement
  private colorSwatch!: HTMLElement

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

    // Color picker row
    const colorRow = document.createElement('div')
    Object.assign(colorRow.style, {
      display: 'flex',
      alignItems: 'center',
      gap: '8px',
      pointerEvents: 'auto',
    })

    this.colorSwatch = document.createElement('div')
    Object.assign(this.colorSwatch.style, {
      width: '14px',
      height: '14px',
      borderRadius: '50%',
      background: COLOR_PRESETS[0].hex,
      border: '2px solid rgba(255,255,255,0.4)',
      flexShrink: '0',
    })

    this.colorSelect = document.createElement('select')
    Object.assign(this.colorSelect.style, {
      background: 'rgba(0,0,0,0.55)',
      color: '#fff',
      border: '1px solid rgba(255,255,255,0.25)',
      borderRadius: '16px',
      padding: '5px 12px',
      fontSize: '13px',
      fontFamily: 'inherit',
      cursor: 'pointer',
      backdropFilter: 'blur(8px)',
      outline: 'none',
      appearance: 'none',
      paddingRight: '28px',
    })

    // Arrow indicator via background image
    this.colorSelect.style.backgroundImage =
      `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23ffffff99'/%3E%3C/svg%3E")`
    this.colorSelect.style.backgroundRepeat = 'no-repeat'
    this.colorSelect.style.backgroundPosition = 'right 10px center'

    for (const preset of COLOR_PRESETS) {
      const opt = document.createElement('option')
      opt.value = preset.label
      opt.textContent = preset.label
      this.colorSelect.appendChild(opt)
    }

    this.colorSelect.addEventListener('change', () => {
      const preset = COLOR_PRESETS.find(p => p.label === this.colorSelect.value)
      if (preset) this.colorSwatch.style.background = preset.hex
    })

    colorRow.appendChild(this.colorSwatch)
    colorRow.appendChild(this.colorSelect)

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
    this.panel.appendChild(colorRow)
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

  getSelectedColor(): Color3 {
    return (COLOR_PRESETS.find(p => p.label === this.colorSelect.value) ?? COLOR_PRESETS[0]).color
  }

  destroy(): void {
    this.onGrowCallback = null
    this.onResetCallback = null
    this.panel.remove()
  }
}
