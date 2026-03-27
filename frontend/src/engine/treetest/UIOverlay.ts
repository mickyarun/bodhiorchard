/**
 * UIOverlay — HTML controls overlay for the tree growth demo.
 *
 * Pure DOM manipulation. Creates a floating panel with:
 * - Color picker (preset bark colors)
 * - Bird / Bee toggle pills
 * - "Grow" / "New Tree" button
 * - "Reset" button
 * - Progress bar during growth
 */
import type { Color3 } from './TreeRules'

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
  private progressBar!: HTMLElement
  private progressFill!: HTMLElement
  private colorSelect!: HTMLSelectElement
  private colorSwatch!: HTMLElement
  private birdsToggle!: HTMLButtonElement
  private beesToggle!: HTMLButtonElement

  private birdsEnabled = true
  private beesEnabled  = true

  private onGrowCallback:         (() => void) | null = null
  private onResetCallback:        (() => void) | null = null
  private onToggleBirdsCallback:  ((on: boolean) => void) | null = null
  private onToggleBeesCallback:   ((on: boolean) => void) | null = null

  // Stored listener refs for proper removeEventListener in destroy()
  private _onColorChange!:  () => void
  private _onGrowEnter!:    () => void
  private _onGrowLeave!:    () => void
  private _onGrowClick!:    () => void
  private _onResetEnter!:   () => void
  private _onResetLeave!:   () => void
  private _onResetClick!:   () => void
  private _onBirdsClick!:   () => void
  private _onBeesClick!:    () => void

  constructor(container: HTMLElement) {
    this.container = container
    this.build()
  }

  private build(): void {
    this.container.style.position = 'relative'

    this.panel = document.createElement('div')
    Object.assign(this.panel.style, {
      position:   'absolute',
      bottom:     '24px',
      left:       '50%',
      transform:  'translateX(-50%)',
      display:    'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap:        '10px',
      zIndex:     '10',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      pointerEvents: 'none',
    })

    // Progress bar
    this.progressBar = document.createElement('div')
    Object.assign(this.progressBar.style, {
      width:      '200px',
      height:     '4px',
      borderRadius: '2px',
      background: 'rgba(255, 255, 255, 0.2)',
      overflow:   'hidden',
      opacity:    '0',
      transition: 'opacity 0.3s',
    })
    this.progressFill = document.createElement('div')
    Object.assign(this.progressFill.style, {
      width:      '0%',
      height:     '100%',
      borderRadius: '2px',
      background: 'linear-gradient(90deg, #4ade80, #22c55e)',
      transition: 'width 0.1s linear',
    })
    this.progressBar.appendChild(this.progressFill)

    // Color picker row
    const colorRow = document.createElement('div')
    Object.assign(colorRow.style, {
      display:    'flex',
      alignItems: 'center',
      gap:        '8px',
      pointerEvents: 'auto',
    })

    this.colorSwatch = document.createElement('div')
    Object.assign(this.colorSwatch.style, {
      width:        '14px',
      height:       '14px',
      borderRadius: '50%',
      background:   COLOR_PRESETS[0].hex,
      border:       '2px solid rgba(255,255,255,0.4)',
      flexShrink:   '0',
    })

    this.colorSelect = document.createElement('select')
    Object.assign(this.colorSelect.style, {
      background:   'rgba(0,0,0,0.55)',
      color:        '#fff',
      border:       '1px solid rgba(255,255,255,0.25)',
      borderRadius: '16px',
      padding:      '5px 12px',
      fontSize:     '13px',
      fontFamily:   'inherit',
      cursor:       'pointer',
      backdropFilter: 'blur(8px)',
      outline:      'none',
      appearance:   'none',
      paddingRight: '28px',
    })
    this.colorSelect.style.backgroundImage =
      `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23ffffff99'/%3E%3C/svg%3E")`
    this.colorSelect.style.backgroundRepeat   = 'no-repeat'
    this.colorSelect.style.backgroundPosition = 'right 10px center'

    for (const preset of COLOR_PRESETS) {
      const opt = document.createElement('option')
      opt.value       = preset.label
      opt.textContent = preset.label
      this.colorSelect.appendChild(opt)
    }

    this._onColorChange = () => {
      const preset = COLOR_PRESETS.find(p => p.label === this.colorSelect.value)
      if (preset) this.colorSwatch.style.background = preset.hex
    }
    this.colorSelect.addEventListener('change', this._onColorChange)

    colorRow.appendChild(this.colorSwatch)
    colorRow.appendChild(this.colorSelect)

    // Creature toggles row
    const toggleRow = document.createElement('div')
    Object.assign(toggleRow.style, {
      display:  'flex',
      gap:      '8px',
      pointerEvents: 'auto',
    })

    this.birdsToggle = this.makeToggleBtn('🦜 Birds', true)
    this.beesToggle  = this.makeToggleBtn('🐝 Bees',  true)

    this._onBirdsClick = () => {
      this.birdsEnabled = !this.birdsEnabled
      this.applyToggleStyle(this.birdsToggle, this.birdsEnabled)
      this.onToggleBirdsCallback?.(this.birdsEnabled)
    }
    this._onBeesClick = () => {
      this.beesEnabled = !this.beesEnabled
      this.applyToggleStyle(this.beesToggle, this.beesEnabled)
      this.onToggleBeesCallback?.(this.beesEnabled)
    }
    this.birdsToggle.addEventListener('click', this._onBirdsClick)
    this.beesToggle.addEventListener('click',  this._onBeesClick)

    toggleRow.appendChild(this.birdsToggle)
    toggleRow.appendChild(this.beesToggle)

    // Main button row
    const btnRow = document.createElement('div')
    Object.assign(btnRow.style, {
      display: 'flex',
      gap:     '10px',
      pointerEvents: 'auto',
    })

    // Grow button
    this.growBtn = document.createElement('button')
    this.growBtn.textContent = 'Grow'
    Object.assign(this.growBtn.style, {
      background:   'linear-gradient(135deg, #22c55e, #16a34a)',
      color:        '#fff',
      border:       'none',
      borderRadius: '24px',
      padding:      '10px 32px',
      fontSize:     '16px',
      fontWeight:   '700',
      cursor:       'pointer',
      boxShadow:    '0 4px 15px rgba(34, 197, 94, 0.4)',
      transition:   'all 0.2s ease',
      letterSpacing: '0.5px',
    })
    this._onGrowEnter = () => {
      if (!this.growBtn.disabled) {
        this.growBtn.style.transform  = 'scale(1.05)'
        this.growBtn.style.boxShadow  = '0 6px 20px rgba(34, 197, 94, 0.5)'
      }
    }
    this._onGrowLeave = () => {
      this.growBtn.style.transform = 'scale(1)'
      this.growBtn.style.boxShadow = '0 4px 15px rgba(34, 197, 94, 0.4)'
    }
    this._onGrowClick = () => this.onGrowCallback?.()
    this.growBtn.addEventListener('mouseenter', this._onGrowEnter)
    this.growBtn.addEventListener('mouseleave', this._onGrowLeave)
    this.growBtn.addEventListener('click',      this._onGrowClick)

    // Reset button
    this.resetBtn = document.createElement('button')
    this.resetBtn.textContent = 'Reset'
    Object.assign(this.resetBtn.style, {
      background:   'rgba(255, 255, 255, 0.15)',
      color:        '#fff',
      border:       '1px solid rgba(255, 255, 255, 0.3)',
      borderRadius: '24px',
      padding:      '10px 20px',
      fontSize:     '14px',
      fontWeight:   '500',
      cursor:       'pointer',
      backdropFilter: 'blur(8px)',
      transition:   'all 0.2s ease',
    })
    this._onResetEnter = () => { this.resetBtn.style.background = 'rgba(255, 255, 255, 0.25)' }
    this._onResetLeave = () => { this.resetBtn.style.background = 'rgba(255, 255, 255, 0.15)' }
    this._onResetClick = () => this.onResetCallback?.()
    this.resetBtn.addEventListener('mouseenter', this._onResetEnter)
    this.resetBtn.addEventListener('mouseleave', this._onResetLeave)
    this.resetBtn.addEventListener('click',      this._onResetClick)

    btnRow.appendChild(this.growBtn)
    btnRow.appendChild(this.resetBtn)

    this.panel.appendChild(this.progressBar)
    this.panel.appendChild(colorRow)
    this.panel.appendChild(toggleRow)
    this.panel.appendChild(btnRow)
    this.container.appendChild(this.panel)
  }

  // ─── Public API ───────────────────────────────────────────────────────────

  onGrow(callback: () => void): void         { this.onGrowCallback = callback }
  onReset(callback: () => void): void        { this.onResetCallback = callback }
  onToggleBirds(cb: (on: boolean) => void):  void { this.onToggleBirdsCallback = cb }
  onToggleBees(cb: (on: boolean) => void):   void { this.onToggleBeesCallback  = cb }

  setGrowEnabled(enabled: boolean): void {
    this.growBtn.disabled        = !enabled
    this.growBtn.style.opacity   = enabled ? '1' : '0.5'
    this.growBtn.style.cursor    = enabled ? 'pointer' : 'not-allowed'
  }

  setGrowLabel(text: string): void {
    this.growBtn.textContent = text
  }

  showProgress(fraction: number): void {
    this.progressBar.style.opacity       = fraction > 0 && fraction < 1 ? '1' : '0'
    this.progressFill.style.width        = `${Math.round(fraction * 100)}%`
  }

  getSelectedColor(): Color3 {
    return (COLOR_PRESETS.find(p => p.label === this.colorSelect.value) ?? COLOR_PRESETS[0]).color
  }

  destroy(): void {
    this.colorSelect.removeEventListener('change',      this._onColorChange)
    this.growBtn.removeEventListener('mouseenter',      this._onGrowEnter)
    this.growBtn.removeEventListener('mouseleave',      this._onGrowLeave)
    this.growBtn.removeEventListener('click',           this._onGrowClick)
    this.resetBtn.removeEventListener('mouseenter',     this._onResetEnter)
    this.resetBtn.removeEventListener('mouseleave',     this._onResetLeave)
    this.resetBtn.removeEventListener('click',          this._onResetClick)
    this.birdsToggle.removeEventListener('click',       this._onBirdsClick)
    this.beesToggle.removeEventListener('click',        this._onBeesClick)
    this.onGrowCallback        = null
    this.onResetCallback       = null
    this.onToggleBirdsCallback = null
    this.onToggleBeesCallback  = null
    this.panel.remove()
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  private makeToggleBtn(label: string, initialOn: boolean): HTMLButtonElement {
    const btn = document.createElement('button')
    btn.textContent = label
    Object.assign(btn.style, {
      border:        '1px solid rgba(255,255,255,0.25)',
      borderRadius:  '16px',
      padding:       '5px 14px',
      fontSize:      '12px',
      fontFamily:    'inherit',
      fontWeight:    '500',
      cursor:        'pointer',
      backdropFilter: 'blur(8px)',
      transition:    'all 0.2s ease',
      color:         '#fff',
      letterSpacing: '0.3px',
    })
    this.applyToggleStyle(btn, initialOn)
    return btn
  }

  private applyToggleStyle(btn: HTMLButtonElement, on: boolean): void {
    btn.style.background = on
      ? 'rgba(255, 255, 255, 0.22)'
      : 'rgba(255, 255, 255, 0.06)'
    btn.style.opacity = on ? '1' : '0.5'
  }
}
