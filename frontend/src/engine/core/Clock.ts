/**
 * Clock — Frame-level time tracking.
 *
 * Provides dt (delta time since last frame) and elapsed (total time).
 * Used by all animated subsystems.
 */

export class Clock {
  /** Seconds since last frame */
  dt = 0

  /** Total elapsed seconds since clock started */
  elapsed = 0

  /** Frames rendered since start */
  frame = 0

  update(dt: number): void {
    this.dt = dt
    this.elapsed += dt
    this.frame++
  }

  reset(): void {
    this.dt = 0
    this.elapsed = 0
    this.frame = 0
  }
}
