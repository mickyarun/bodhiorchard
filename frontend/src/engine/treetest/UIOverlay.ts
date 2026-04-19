// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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

const FEATURE_COUNTS: readonly number[][] = [[3, 10, 20, 50], [100, 150, 200, 250]]

const COLOR_PRESETS: { label: string; color: Color3; hex: string }[] = [
  { label: 'Cyan',    color: [  0, 180, 200], hex: '#00b4c8' },
  { label: 'Jade',    color: [  0, 200, 120], hex: '#00c878' },
  { label: 'Gold',    color: [220, 160,   0], hex: '#dca000' },
  { label: 'Azure',   color: [ 80, 140, 255], hex: '#508cff' },
  { label: 'Rose',    color: [220,  80, 140], hex: '#dc508c' },
  { label: 'Violet',  color: [160,  80, 255], hex: '#a050ff' },
]

export class UIOverlay {
  private readonly container: HTMLElement
  private panel!: HTMLElement
  private growBtn!: HTMLButtonElement
  private resetBtn!: HTMLButtonElement
  private progressBar!: HTMLElement
  private progressFill!: HTMLElement
  private colorSelect!: HTMLSelectElement
  private colorSwatch!: HTMLElement
  private birdsToggle!: HTMLButtonElement
  private beesToggle!: HTMLButtonElement
  private featureBtns: HTMLButtonElement[] = []
  private windSlider!: HTMLInputElement
  private windLabel!: HTMLSpanElement

  private birdsEnabled = true
  private beesEnabled  = true

  // Feature hover tooltip — built in build(), owned here so index.ts has no DOM dependency
  private tooltipEl!:     HTMLDivElement
  private tooltipTitle!:  HTMLSpanElement
  private tooltipStatus!: HTMLSpanElement
  private tooltipDot!:    HTMLSpanElement

  private onGrowCallback:           (() => void) | null = null
  private onResetCallback:          (() => void) | null = null
  private onToggleBirdsCallback:    ((on: boolean) => void) | null = null
  private onToggleBeesCallback:     ((on: boolean) => void) | null = null
  private onLoadFeaturesCallback:   ((count: number) => void) | null = null
  private onWindStrengthCallback:   ((strength: number) => void) | null = null

  // Stored listener refs for proper removeEventListener in destroy()
  private _onColorChange!:     () => void
  private _onGrowEnter!:       () => void
  private _onGrowLeave!:       () => void
  private _onGrowClick!:       () => void
  private _onResetEnter!:      () => void
  private _onResetLeave!:      () => void
  private _onResetClick!:      () => void
  private _onBirdsClick!:      () => void
  private _onBeesClick!:       () => void
  private _onWindInput!:       () => void
  private _onWindPointerDown!: (e: Event) => void
  private _onWindPointerMove!: (e: Event) => void
  private _onWindMouseDown!:   (e: Event) => void
  private _onWindMouseMove!:   (e: Event) => void
  private _onFeatureClicks:    (() => void)[] = []

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

    // Wind strength slider row
    const windRow = document.createElement('div')
    Object.assign(windRow.style, {
      display:       'flex',
      alignItems:    'center',
      gap:           '8px',
      pointerEvents: 'auto',
    })

    this.windLabel = document.createElement('span')
    this.windLabel.textContent = 'Wind 40%'
    Object.assign(this.windLabel.style, {
      color:      'rgba(255,255,255,0.6)',
      fontSize:   '11px',
      fontWeight: '500',
      minWidth:   '58px',
      letterSpacing: '0.3px',
    })

    this.windSlider = document.createElement('input')
    this.windSlider.type  = 'range'
    this.windSlider.min   = '0'
    this.windSlider.max   = '100'
    this.windSlider.value = '40'
    Object.assign(this.windSlider.style, {
      width:       '100px',
      accentColor: '#82c8ff',
      cursor:      'pointer',
    })

    this._onWindInput = () => {
      const v = parseInt(this.windSlider.value, 10)
      this.windLabel.textContent = `Wind ${v}%`
      this.onWindStrengthCallback?.(v / 100)
    }
    this.windSlider.addEventListener('input', this._onWindInput)
    // Prevent slider drag from reaching the canvas InputManager (which would orbit the camera)
    this._onWindPointerDown = (e) => e.stopPropagation()
    this._onWindPointerMove = (e) => e.stopPropagation()
    this._onWindMouseDown   = (e) => e.stopPropagation()
    this._onWindMouseMove   = (e) => e.stopPropagation()
    this.windSlider.addEventListener('pointerdown', this._onWindPointerDown)
    this.windSlider.addEventListener('pointermove', this._onWindPointerMove)
    this.windSlider.addEventListener('mousedown',   this._onWindMouseDown)
    this.windSlider.addEventListener('mousemove',   this._onWindMouseMove)

    windRow.appendChild(this.windLabel)
    windRow.appendChild(this.windSlider)

    // Feature count rows (two rows: small counts and large counts)
    const featRow = document.createElement('div')
    Object.assign(featRow.style, {
      display:    'flex',
      alignItems: 'flex-start',
      gap:        '6px',
      pointerEvents: 'auto',
    })

    const featLabel = document.createElement('span')
    featLabel.textContent = 'Features'
    Object.assign(featLabel.style, {
      color:      'rgba(255,255,255,0.5)',
      fontSize:   '11px',
      fontWeight: '500',
      letterSpacing: '0.4px',
      paddingTop: '4px',
    })
    featRow.appendChild(featLabel)

    const featColumn = document.createElement('div')
    Object.assign(featColumn.style, {
      display:       'flex',
      flexDirection: 'column',
      gap:           '5px',
    })

    for (const rowCounts of FEATURE_COUNTS) {
      const row = document.createElement('div')
      Object.assign(row.style, { display: 'flex', gap: '6px' })
      for (const count of rowCounts) {
        const btn = document.createElement('button')
        btn.textContent = String(count)
        Object.assign(btn.style, {
          background:   'rgba(255,255,255,0.1)',
          color:        '#fff',
          border:       '1px solid rgba(255,255,255,0.2)',
          borderRadius: '12px',
          padding:      '3px 10px',
          fontSize:     '12px',
          fontWeight:   '600',
          cursor:       'pointer',
          backdropFilter: 'blur(8px)',
          transition:   'all 0.15s ease',
          minWidth:     '36px',
        })
        const handler = () => {
          // Highlight active button
          for (const b of this.featureBtns) {
            b.style.background = 'rgba(255,255,255,0.1)'
            b.style.border     = '1px solid rgba(255,255,255,0.2)'
          }
          btn.style.background = 'rgba(130,200,255,0.25)'
          btn.style.border     = '1px solid rgba(130,200,255,0.5)'
          this.onLoadFeaturesCallback?.(count)
        }
        this._onFeatureClicks.push(handler)
        btn.addEventListener('click', handler)
        this.featureBtns.push(btn)
        row.appendChild(btn)
      }
      featColumn.appendChild(row)
    }
    featRow.appendChild(featColumn)

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
    this.panel.appendChild(windRow)
    this.panel.appendChild(featRow)
    this.panel.appendChild(btnRow)
    this.container.appendChild(this.panel)

    // Feature hover tooltip — purely via DOM methods, no innerHTML
    this.tooltipEl = document.createElement('div')
    Object.assign(this.tooltipEl.style, {
      position:       'absolute',
      pointerEvents:  'none',
      display:        'none',
      background:     'rgba(10, 10, 20, 0.85)',
      color:          '#fff',
      border:         '1px solid rgba(255,255,255,0.15)',
      borderRadius:   '8px',
      padding:        '7px 12px',
      fontSize:       '13px',
      fontFamily:     'system-ui, -apple-system, sans-serif',
      backdropFilter: 'blur(8px)',
      whiteSpace:     'nowrap',
      zIndex:         '20',
      lineHeight:     '1.5',
    })
    this.tooltipTitle = document.createElement('span')
    this.tooltipTitle.style.fontWeight = '700'

    const statusLine = document.createElement('div')
    Object.assign(statusLine.style, { fontSize: '11px', opacity: '0.75' })

    this.tooltipDot    = document.createElement('span')
    this.tooltipStatus = document.createElement('span')
    statusLine.appendChild(this.tooltipDot)
    statusLine.appendChild(this.tooltipStatus)

    this.tooltipEl.appendChild(this.tooltipTitle)
    this.tooltipEl.appendChild(statusLine)
    this.container.appendChild(this.tooltipEl)
  }

  // ─── Public API ───────────────────────────────────────────────────────────

  onGrow(callback: () => void): void         { this.onGrowCallback = callback }
  onReset(callback: () => void): void        { this.onResetCallback = callback }
  onToggleBirds(cb: (on: boolean) => void):  void { this.onToggleBirdsCallback   = cb }
  onToggleBees(cb: (on: boolean) => void):   void { this.onToggleBeesCallback    = cb }
  onLoadFeatures(cb: (count: number) => void): void { this.onLoadFeaturesCallback = cb }
  onWindStrength(cb: (strength: number) => void): void { this.onWindStrengthCallback = cb }

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

  /** Show the feature hover tooltip at canvas-relative (x, y). */
  showFeatureTooltip(title: string, status: string, x: number, y: number): void {
    this.tooltipTitle.textContent  = title
    this.tooltipStatus.textContent = ' ' + status.replace('_', ' ')
    this.tooltipDot.textContent    = '● '
    this.tooltipDot.style.color    =
      status === 'planned'     ? '#3cc850' :
      status === 'in_progress' ? '#f09628' : '#dc3232'

    this.tooltipEl.style.display = 'block'

    // Clamp so tooltip stays inside the container
    const tw   = this.tooltipEl.offsetWidth  || 160
    const th   = this.tooltipEl.offsetHeight || 48
    const cw   = this.container.clientWidth
    const left = Math.min(x + 14, cw - tw - 8)
    const top  = Math.max(y - th - 14, 8)
    this.tooltipEl.style.left = `${left}px`
    this.tooltipEl.style.top  = `${top}px`
  }

  hideFeatureTooltip(): void {
    this.tooltipEl.style.display = 'none'
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
    this.windSlider.removeEventListener('input',        this._onWindInput)
    this.windSlider.removeEventListener('pointerdown',  this._onWindPointerDown)
    this.windSlider.removeEventListener('pointermove',  this._onWindPointerMove)
    this.windSlider.removeEventListener('mousedown',    this._onWindMouseDown)
    this.windSlider.removeEventListener('mousemove',    this._onWindMouseMove)
    this.featureBtns.forEach((btn, i) => btn.removeEventListener('click', this._onFeatureClicks[i]))
    this.featureBtns     = []
    this._onFeatureClicks = []
    this.onGrowCallback         = null
    this.onResetCallback        = null
    this.onToggleBirdsCallback  = null
    this.onToggleBeesCallback   = null
    this.onLoadFeaturesCallback = null
    this.onWindStrengthCallback = null
    this.tooltipEl.remove()
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
