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
    try {
      // Fade in. Re-check overlay after each await — destroy() can null it
      // mid-flight if a teardown races with an in-progress transition.
      this.overlay.style.display = 'block'
      await this.nextFrame()
      if (!this.overlay) return
      this.overlay.style.opacity = '1'
      await this.wait(FADE_MS)

      // Swap (happens while black — await supports async callbacks like interior build)
      await onSwap()

      // Fade out
      if (!this.overlay) return
      this.overlay.style.opacity = '0'
      await this.wait(FADE_MS)
      if (!this.overlay) return
      this.overlay.style.display = 'none'
    } finally {
      this.active = false
    }
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
