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
 * TVEffect — flickering point light that simulates a TV playing.
 *
 * Creates a PlayCanvas point light positioned in front of the TV screen face.
 * Cycles through content "channels" (news, movie, nature, action, sci-fi)
 * by randomizing color and intensity to simulate programme changes.
 *
 * TV is at (3.6, 0, 3.0) with rotation=270° → screen faces -X (into room).
 * Light sits between the screen and the lounge chair.
 *
 * Driven by update(dt) from the engine loop — no setInterval, so it stays
 * in sync with the PlayCanvas frame rate and cleans up correctly on destroy().
 */
import * as pc from 'playcanvas'

// Position in front of the TV screen face (screen faces -X, light at lower X)
const LIGHT_X     = 3.0
const LIGHT_Y     = 0.75
const LIGHT_Z     = 3.0
const LIGHT_RANGE = 4.5

const FLICKER_INTERVAL = 0.1   // seconds between flicker ticks (~10fps)

// Min/max seconds before switching to the next channel (~3–7s)
const CHANNEL_SWITCH_MIN = 3.0
const CHANNEL_SWITCH_MAX = 7.0

// Each channel: [r, g, b, baseIntensity]
// Palette simulates different TV content by cycling through distinct colour casts.
const CHANNELS: Array<[number, number, number, number]> = [
  [0.40, 0.55, 1.00, 1.2],  // cool blue    — news / talk show
  [1.00, 0.70, 0.30, 1.0],  // warm orange  — movie / fire scene
  [0.30, 0.90, 0.35, 1.1],  // green        — nature documentary
  [0.90, 0.28, 0.22, 1.3],  // red          — action / thriller
  [0.75, 0.55, 1.00, 1.0],  // purple       — sci-fi
  [1.00, 0.95, 0.80, 1.5],  // bright white — commercial flash
]

export class TVEffect {
  private lightEntity:   pc.Entity | null = null
  private active         = false
  private flickerAccum   = 0   // seconds since last flicker tick
  private channelAccum   = 0   // seconds since last channel switch
  private nextChannelAt  = CHANNEL_SWITCH_MIN
  private channelIdx     = 0

  /** Call once after the interior root entity is available. */
  init(root: pc.Entity): void {
    const e = new pc.Entity('TVLight')
    e.addComponent('light', {
      type: 'point',
      color: new pc.Color(...(CHANNELS[0].slice(0, 3) as [number, number, number])),
      intensity: 0,         // off until turnOn()
      range: LIGHT_RANGE,
      castShadows: false,   // no shadows — lightweight room-fill effect
    })
    e.setLocalPosition(LIGHT_X, LIGHT_Y, LIGHT_Z)
    root.addChild(e)
    this.lightEntity = e
  }

  /** Start the TV playing effect. */
  turnOn(): void {
    if (!this.lightEntity) return
    this.active        = true
    this.channelIdx    = 0
    this.flickerAccum  = 0
    this.channelAccum  = 0
    this.nextChannelAt = this.randomChannelDuration()
    const [r, g, b, intensity] = CHANNELS[0]
    this.lightEntity.light!.color     = new pc.Color(r, g, b)
    this.lightEntity.light!.intensity = intensity
  }

  /** Stop the TV — light goes dark. */
  turnOff(): void {
    this.active = false
    if (this.lightEntity) this.lightEntity.light!.intensity = 0
  }

  /**
   * Call every frame from the engine's onUpdate loop.
   * dt is the frame delta in seconds (same value PlayCanvas passes to scripts).
   */
  update(dt: number): void {
    if (!this.active || !this.lightEntity) return

    this.flickerAccum  += dt
    this.channelAccum  += dt

    // Flicker tick
    if (this.flickerAccum >= FLICKER_INTERVAL) {
      this.flickerAccum -= FLICKER_INTERVAL
      this.applyFlicker()
    }

    // Channel switch
    if (this.channelAccum >= this.nextChannelAt) {
      this.channelAccum  = 0
      this.nextChannelAt = this.randomChannelDuration()
      this.channelIdx    = (this.channelIdx + 1) % CHANNELS.length
      const [r, g, b, base] = CHANNELS[this.channelIdx]
      this.lightEntity.light!.color = new pc.Color(r, g, b)
      // Occasional bright flash on channel change (simulates hard cut / transition)
      this.lightEntity.light!.intensity = base * (Math.random() < 0.4 ? 2.2 : 1.0)
    }
  }

  destroy(): void {
    this.active = false
    this.lightEntity?.destroy()
    this.lightEntity = null
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  private applyFlicker(): void {
    if (!this.lightEntity) return
    const [r, g, b, base] = CHANNELS[this.channelIdx]
    this.lightEntity.light!.color     = new pc.Color(r, g, b)
    // Intensity jitter ±20% around channel base
    this.lightEntity.light!.intensity = base * (0.82 + Math.random() * 0.38)
  }

  private randomChannelDuration(): number {
    return CHANNEL_SWITCH_MIN + Math.random() * (CHANNEL_SWITCH_MAX - CHANNEL_SWITCH_MIN)
  }
}
