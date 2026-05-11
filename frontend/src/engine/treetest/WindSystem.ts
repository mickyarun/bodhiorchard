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
 * WindSystem — drives coherent wind animation for branches and leaves.
 *
 * Design:
 *   - Natural gust dynamics: wind arrives in random bursts then fades to calm
 *   - Each tree gets a unique spatial phase from its world position
 *   - Multi-frequency sine composition within each gust for organic motion
 *   - Zero allocation in update path
 *
 * Gust lifecycle:
 *   CALM → ramp up (0.5-1s) → GUSTING (2-5s) → ramp down (1-2s) → CALM (2-6s) → repeat
 *   Each gust has a random peak strength and slightly randomized direction.
 */

export interface WindConfig {
  /** Max wind strength 0–1. 0 = disabled, 0.3 = gentle breeze, 1 = storm */
  strength: number
  /** Base wind direction in radians (0 = +X). Gusts drift ±30° around this. */
  direction: number
}

const DEFAULT_CONFIG: WindConfig = {
  strength: 0.4,
  direction: 0,
}

// ─── Gust timing ─────────────────────────────────────────────────────────────
const CALM_MIN       = 2.0    // seconds of calm between gusts
const CALM_MAX       = 6.0
const GUST_MIN       = 2.0    // seconds a gust lasts at peak
const GUST_MAX       = 5.0
const RAMP_UP_MIN    = 0.5    // seconds to ramp from calm to peak
const RAMP_UP_MAX    = 1.0
const RAMP_DOWN_MIN  = 1.0    // seconds to ramp from peak to calm
const RAMP_DOWN_MAX  = 2.0
const GUST_STRENGTH_MIN = 0.3  // min peak as fraction of config.strength
const GUST_STRENGTH_MAX = 1.0  // max peak as fraction of config.strength
const DIRECTION_DRIFT   = Math.PI / 6  // ±30° random drift per gust

// ─── Sway frequencies ────────────────────────────────────────────────────────
const SWAY_FREQ_1    = 0.31   // primary sway — ~3.2s period
const SWAY_FREQ_2    = 0.73   // secondary — ~1.4s, creates irregularity
const SWAY_FREQ_3    = 1.53   // shimmer — ~0.65s (mostly for leaves)
const AMP_1          = 0.60
const AMP_2          = 0.28
const AMP_3          = 0.12

// Max sway angle in degrees at strength=1
const MAX_BRANCH_SWAY_DEG = 4    // whole-tree tilt — subtle
const MAX_LEAF_SWAY_DEG   = 15   // leaf flutter — max per user feedback

// Spatial frequency — how fast the wave rolls across space
const SPATIAL_FREQ = 0.5

// ─── Gust state machine ─────────────────────────────────────────────────────
const enum GustPhase { CALM, RAMP_UP, GUSTING, RAMP_DOWN }

function randRange(min: number, max: number): number {
  return min + Math.random() * (max - min)
}

export class WindSystem {
  private config: WindConfig
  private time = 0

  // Gust state
  private phase: GustPhase = GustPhase.CALM
  private phaseTimer = 0
  private phaseDuration = randRange(CALM_MIN, CALM_MAX)
  private gustPeak = 0       // 0..1 — peak strength of current gust (fraction of config.strength)
  private gustDir = 0        // actual direction during this gust
  private gustEnvelope = 0   // 0..1 — current gust intensity (smoothly ramped)

  constructor(config?: Partial<WindConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config }
    this.gustDir = this.config.direction
  }

  /** Call once per frame. */
  update(dt: number): void {
    this.time += dt
    this.advanceGust(dt)
  }

  /** Current wind strength (0–1). */
  getStrength(): number { return this.config.strength }

  /** Set wind strength (0–1). */
  setStrength(s: number): void { this.config.strength = Math.max(0, Math.min(1, s)) }

  /** Wind direction in radians (current gust-adjusted direction). */
  getDirection(): number { return this.gustDir }

  /** Set base wind direction in radians. */
  setDirection(rad: number): void { this.config.direction = rad }

  /** Current elapsed time — for consumers that need raw time. */
  getTime(): number { return this.time }

  /**
   * Compute sway angle (degrees) for a tree trunk (whole-tree tilt).
   *
   * @param worldX — tree world X (spatial phase offset)
   * @param worldZ — tree world Z
   * @param heightFactor — 0 at ground, 1 at canopy. Controls amplitude.
   * @param sizeFactor   — branch.size / rootSize. 0=tiny, 1=trunk.
   */
  getBranchSway(worldX: number, worldZ: number, heightFactor: number, sizeFactor: number): number {
    if (this.config.strength <= 0 || this.gustEnvelope <= 0.001) return 0

    const spatialPhase = (worldX * Math.cos(this.gustDir) +
                          worldZ * Math.sin(this.gustDir)) * SPATIAL_FREQ

    const flexibility = 1.0 - 0.9 * sizeFactor
    const heightScale = 0.15 + 0.85 * heightFactor

    const t = this.time
    const sway = Math.sin(t * SWAY_FREQ_1 * Math.PI * 2 + spatialPhase) * AMP_1 +
                 Math.sin(t * SWAY_FREQ_2 * Math.PI * 2 + spatialPhase * 1.4) * AMP_2

    return sway * MAX_BRANCH_SWAY_DEG * this.config.strength * this.gustEnvelope *
           flexibility * heightScale
  }

  /**
   * Compute sway angles (pitch, roll) for a leaf entity.
   *
   * @param worldX — world X position
   * @param worldZ — world Z position
   * @param leafPhase — per-leaf random phase offset (0..2PI)
   */
  getLeafSway(worldX: number, worldZ: number, leafPhase: number): [number, number] {
    if (this.config.strength <= 0 || this.gustEnvelope <= 0.001) return [0, 0]

    const spatialPhase = (worldX * Math.cos(this.gustDir) +
                          worldZ * Math.sin(this.gustDir)) * SPATIAL_FREQ

    const t = this.time
    const phase = spatialPhase + leafPhase

    const pitch = (
      Math.sin(t * SWAY_FREQ_1 * Math.PI * 2 + phase) * AMP_1 +
      Math.sin(t * SWAY_FREQ_2 * Math.PI * 2 + phase * 1.4) * AMP_2 +
      Math.sin(t * SWAY_FREQ_3 * Math.PI * 2 + phase * 2.3) * AMP_3
    ) * MAX_LEAF_SWAY_DEG * this.config.strength * this.gustEnvelope

    const roll = (
      Math.cos(t * SWAY_FREQ_1 * 0.87 * Math.PI * 2 + phase * 0.9) * AMP_1 +
      Math.cos(t * SWAY_FREQ_2 * 1.1 * Math.PI * 2 + phase * 1.6) * AMP_2 * 0.7
    ) * MAX_LEAF_SWAY_DEG * this.config.strength * this.gustEnvelope * 0.5

    return [pitch, roll]
  }

  // ─── Gust state machine ──────────────────────────────────────────────────────

  private advanceGust(dt: number): void {
    this.phaseTimer += dt

    if (this.phaseTimer >= this.phaseDuration) {
      this.phaseTimer = 0
      this.transitionToNextPhase()
    }

    // Compute gustEnvelope based on current phase
    const progress = this.phaseDuration > 0 ? this.phaseTimer / this.phaseDuration : 0
    switch (this.phase) {
      case GustPhase.CALM:
        this.gustEnvelope = 0
        break
      case GustPhase.RAMP_UP:
        // Smooth ease-in: cubic
        this.gustEnvelope = this.gustPeak * progress * progress * (3 - 2 * progress)
        break
      case GustPhase.GUSTING:
        // Hold at peak with slight wobble for organic feel
        this.gustEnvelope = this.gustPeak * (0.85 + 0.15 * Math.sin(this.time * 1.7))
        break
      case GustPhase.RAMP_DOWN:
        // Smooth ease-out: cubic
        const inv = 1 - progress
        this.gustEnvelope = this.gustPeak * inv * inv * (3 - 2 * inv)
        break
    }
  }

  private transitionToNextPhase(): void {
    switch (this.phase) {
      case GustPhase.CALM:
        // Start a new gust
        this.phase = GustPhase.RAMP_UP
        this.phaseDuration = randRange(RAMP_UP_MIN, RAMP_UP_MAX)
        this.gustPeak = randRange(GUST_STRENGTH_MIN, GUST_STRENGTH_MAX)
        // Slightly randomize direction for this gust
        this.gustDir = this.config.direction + (Math.random() - 0.5) * 2 * DIRECTION_DRIFT
        break
      case GustPhase.RAMP_UP:
        this.phase = GustPhase.GUSTING
        this.phaseDuration = randRange(GUST_MIN, GUST_MAX)
        break
      case GustPhase.GUSTING:
        this.phase = GustPhase.RAMP_DOWN
        this.phaseDuration = randRange(RAMP_DOWN_MIN, RAMP_DOWN_MAX)
        break
      case GustPhase.RAMP_DOWN:
        this.phase = GustPhase.CALM
        this.phaseDuration = randRange(CALM_MIN, CALM_MAX)
        break
    }
  }
}
