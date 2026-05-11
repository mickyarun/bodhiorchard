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

    this.makeLabel('WASD — Move   E — Interact   P — Pool   Drag — Orbit   Scroll — Zoom', {
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

  setScene(scene: 'exterior' | 'interior' | 'pool'): void {
    if (this.sceneLabel) {
      const labels: Record<string, string> = { exterior: 'EXTERIOR', interior: 'INTERIOR', pool: 'POOL (SeatProber)' }
      this.sceneLabel.textContent = labels[scene] ?? scene.toUpperCase()
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

  /** Callback for member count slider changes. */
  onMemberCountChange: ((count: number) => void) | null = null

  /** Show a member count slider (top-left). */
  showMemberCountSlider(initial: number): void {
    if (!this.container) return
    const wrapper = document.createElement('div')
    Object.assign(wrapper.style, {
      position: 'absolute', top: '16px', left: '16px',
      background: 'rgba(0,0,0,0.6)', color: '#fff',
      padding: '8px 14px', borderRadius: '10px',
      fontSize: '12px', pointerEvents: 'auto',
      display: 'flex', alignItems: 'center', gap: '8px',
    })

    const label = document.createElement('span')
    label.textContent = 'Members:'
    wrapper.appendChild(label)

    const slider = document.createElement('input')
    slider.type = 'range'
    slider.min = '1'
    slider.max = '60'
    slider.value = String(initial)
    Object.assign(slider.style, { width: '120px', cursor: 'pointer' })
    wrapper.appendChild(slider)

    const valueLabel = document.createElement('span')
    valueLabel.textContent = String(initial)
    valueLabel.style.minWidth = '24px'
    wrapper.appendChild(valueLabel)

    slider.oninput = () => {
      valueLabel.textContent = slider.value
    }
    slider.onchange = () => {
      this.onMemberCountChange?.(parseInt(slider.value, 10))
    }
    this.container.appendChild(wrapper)
  }

  /** Callback set by HouseTestEngine when player presses an anim button. */
  onAnimSelect: ((name: string) => void) | null = null

  /** Show the animation picker panel with buttons for each animation. */
  showAnimPicker(states: string[]): void {
    if (!this.container || this.animPanel) return
    this.animPanel = document.createElement('div')
    Object.assign(this.animPanel.style, {
      position: 'absolute', top: '50px', right: '10px',
      background: 'rgba(0,0,0,0.7)', color: '#fff',
      padding: '8px', borderRadius: '8px',
      display: 'flex', flexDirection: 'column', gap: '4px',
      pointerEvents: 'auto', maxHeight: '80vh', overflowY: 'auto',
      fontSize: '12px',
    })
    const title = document.createElement('div')
    title.textContent = 'Animations'
    Object.assign(title.style, { fontWeight: 'bold', marginBottom: '4px', textAlign: 'center' })
    this.animPanel.appendChild(title)

    for (const name of states) {
      const btn = document.createElement('button')
      btn.textContent = name
      Object.assign(btn.style, {
        background: 'rgba(255,255,255,0.15)', color: '#fff', border: 'none',
        padding: '4px 8px', borderRadius: '4px', cursor: 'pointer',
        fontSize: '11px', textAlign: 'left',
      })
      btn.onmouseenter = () => { btn.style.background = 'rgba(255,255,255,0.3)' }
      btn.onmouseleave = () => { btn.style.background = 'rgba(255,255,255,0.15)' }
      btn.onclick = () => this.onAnimSelect?.(name)
      this.animPanel.appendChild(btn)
    }
    this.container.appendChild(this.animPanel)
  }

  private animPanel: HTMLElement | null = null

  destroy(): void {
    if (this.promptTimeout) clearTimeout(this.promptTimeout)
    this.animPanel?.remove()
    this.container?.remove()
    this.container = null
    this.sceneLabel = null
    this.prompt = null
    this.infoText = null
    this.animPanel = null
  }

  private makeLabel(text: string, styles: Partial<CSSStyleDeclaration>): HTMLElement {
    const el = document.createElement('div')
    el.textContent = text
    Object.assign(el.style, styles)
    this.container!.appendChild(el)
    return el
  }
}
