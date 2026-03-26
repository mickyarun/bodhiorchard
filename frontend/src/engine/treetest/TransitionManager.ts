/**
 * TransitionManager — lightweight frame-based tween system.
 *
 * Each tween lerps a single numeric value from `from` to `to`
 * over `duration` seconds, calling `applyFn` each frame with the
 * interpolated value. Supports delay and custom easing.
 *
 * No external dependencies — uses engine's MathUtils easings.
 */
import { easeOutCubic } from '../utils/MathUtils'

export interface Tween {
  from: number
  to: number
  duration: number
  elapsed: number
  delay: number
  easeFn: (t: number) => number
  applyFn: (value: number) => void
  onComplete?: () => void
}

export class TransitionManager {
  private tweens: Tween[] = []

  /** Enqueue a new tween. */
  add(tween: Partial<Tween> & Pick<Tween, 'from' | 'to' | 'duration' | 'applyFn'>): void {
    this.tweens.push({
      elapsed: 0,
      delay: 0,
      easeFn: easeOutCubic,
      ...tween,
    })
  }

  /** Convenience: animate a value with staggered delay. */
  addStaggered(
    items: Array<{ from: number; to: number; applyFn: (v: number) => void; onComplete?: () => void }>,
    duration: number,
    staggerMs: number,
    easeFn: (t: number) => number = easeOutCubic,
  ): void {
    items.forEach((item, i) => {
      this.add({
        ...item,
        duration,
        delay: i * (staggerMs / 1000),
        easeFn,
      })
    })
  }

  /** Advance all active tweens. Call once per frame. */
  update(dt: number): void {
    for (let i = this.tweens.length - 1; i >= 0; i--) {
      const tw = this.tweens[i]

      // Handle delay
      if (tw.delay > 0) {
        tw.delay -= dt
        continue
      }

      tw.elapsed += dt
      const rawT = Math.min(tw.elapsed / tw.duration, 1)
      const easedT = tw.easeFn(rawT)
      const value = tw.from + (tw.to - tw.from) * easedT
      tw.applyFn(value)

      if (rawT >= 1) {
        tw.onComplete?.()
        this.tweens.splice(i, 1)
      }
    }
  }

  /** True if any tweens are still running. */
  isActive(): boolean {
    return this.tweens.length > 0
  }

  /** Cancel all active tweens. */
  clear(): void {
    this.tweens.length = 0
  }
}
