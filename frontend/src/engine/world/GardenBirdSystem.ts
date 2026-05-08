// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * GardenBirdSystem — 3 parrots that roam the garden autonomously.
 *
 * State machine per bird (industry standard FSM for individual wildlife):
 *
 *   idle → approach → landing → perching → flying_off → idle
 *
 *   idle:        Hidden. Countdown timer. On expire: pick a random repo tree → approach.
 *   approach:    Fly at full speed toward approach waypoint (above perch). Arc in from entry point.
 *   landing:     Slow descent to final perch. Wing amplitude fades — natural wing-tuck.
 *   perching:    Sit still with slow flutter. Timer 5–15 s then fly off.
 *   flying_off:  Fly to random exit point far away, then hide → idle.
 *
 * Two-phase landing (approach → landing) makes birds arc above then descend rather than
 * darting straight at a branch — standard technique per aerodynamic modeling research.
 *
 * Animation: purely procedural (no AnimComponent) — same safe pattern as BirdSystem.ts.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'

// ─── Constants ────────────────────────────────────────────────────────────────

const GLB_PATH        = 'assets/garden/animal-parrot.glb'
const BIRD_COUNT      = 3
const BIRD_SCALE      = 0.6
const MODEL_YAW       = 180        // GLB faces +Z; we use -Z convention

const FLIGHT_SPEED    = 8.0        // world units/sec — cruise
const LAND_SPEED      = 3.0        // world units/sec — final descent
const APPROACH_DIST   = 0.6        // switch approach→landing when this close to approach wp
const PERCH_DIST      = 0.4        // snap to perch when this close
const EXIT_RADIUS     = 30         // hide bird when this far from origin

const SPAWN_RADIUS    = 35         // entry / exit point distance from origin
const SPAWN_Y         = 12         // altitude of entry / exit points
const APPROACH_ABOVE  = 3          // approach waypoint height above final perch

/** Per-bird perch height above tree base (world units). */
const PERCH_Y_ABOVE   = [6, 7, 5] as const

/** Staggered initial idle timers — birds never all arrive together. */
const IDLE_DELAYS     = [3, 10, 17] as const

const PERCH_TIME_MIN  = 5          // s
const PERCH_TIME_MAX  = 15         // s
const IDLE_TIME_MIN   = 8          // s after flying off before next visit
const IDLE_TIME_MAX   = 22         // s

const FLAP_FLIGHT_HZ  = 4.5
const FLAP_FLIGHT_AMP = 32         // degrees
const FLAP_PERCH_HZ   = 0.8
const FLAP_PERCH_AMP  = 8          // degrees

// ─── Types ────────────────────────────────────────────────────────────────────

type BirdState = 'idle' | 'approach' | 'landing' | 'perching' | 'flying_off'

interface GardenBirdEntry {
  entity:      pc.Entity
  wingL:       pc.GraphNode | null
  wingR:       pc.GraphNode | null
  state:       BirdState
  timer:       number           // idle / perch countdown
  pos:         pc.Vec3          // current world position (mutated each frame)
  target:      pc.Vec3          // active fly-to point
  perchTarget: pc.Vec3          // final perch (set during approach, used in landing)
  flapPhase:   number           // per-bird wing phase
  elapsed:     number           // total time alive (for flap oscillation)
}

// ─── System ───────────────────────────────────────────────────────────────────

export class GardenBirdSystem {
  private root:    pc.Entity
  private birds:   GardenBirdEntry[] = []
  private asset:   pc.Asset | null = null
  private perches: pc.Vec3[] = []   // one per repo tree
  private updateAccum = 0   // dt accumulator — system ticks at 30Hz, not 60

  // Scratch — zero allocation in update hot path
  private readonly _diff = new pc.Vec3()

  constructor(app: pc.AppBase) {
    this.root = new pc.Entity('GardenBirds')
    app.root.addChild(this.root)
  }

  async init(loader: AssetLoader): Promise<void> {
    try {
      this.asset = await loader.load(GLB_PATH)
    } catch (e) {
      console.warn('[GardenBirdSystem] Failed to load parrot GLB — birds disabled.', e)
      return
    }

    for (let i = 0; i < BIRD_COUNT; i++) {
      const entity = loader.instance(this.asset)
      entity.setLocalScale(BIRD_SCALE, BIRD_SCALE, BIRD_SCALE)
      entity.enabled = false
      this.root.addChild(entity)

      this.birds.push({
        entity,
        wingL:       entity.findByName('wing-left')  ?? null,
        wingR:       entity.findByName('wing-right') ?? null,
        state:       'idle',
        timer:       IDLE_DELAYS[i],
        pos:         new pc.Vec3(0, SPAWN_Y, 0),
        target:      new pc.Vec3(),
        perchTarget: new pc.Vec3(),
        flapPhase:   Math.random() * Math.PI * 2,
        elapsed:     0,
      })
    }
  }

  /** Supply repo tree positions so birds have perch targets. */
  setTrees(treeMap: Map<string, pc.Entity>): void {
    this.perches = []
    for (const entity of treeMap.values()) {
      const p = entity.getPosition()
      this.perches.push(new pc.Vec3(p.x, p.y, p.z))
    }
  }

  /** Per-frame update — ticks each bird's state machine. Throttled to 30Hz. */
  update(dt: number): void {
    if (this.birds.length === 0 || this.perches.length === 0) return

    // 30Hz throttle. State handlers consume dt linearly (timer -= dt,
    // pos += speed*dt) so passing accumulated dt every other frame is
    // mathematically equivalent. 30Hz keeps flight motion visibly smooth.
    this.updateAccum += dt
    if (this.updateAccum < 1 / 30) return
    const stepDt = this.updateAccum
    this.updateAccum = 0

    for (let i = 0; i < this.birds.length; i++) {
      const bird = this.birds[i]
      bird.elapsed += stepDt

      switch (bird.state) {
        case 'idle':       this.tickIdle(bird, i, stepDt);       break
        case 'approach':   this.tickApproach(bird, stepDt);      break
        case 'landing':    this.tickLanding(bird, stepDt);       break
        case 'perching':   this.tickPerching(bird, stepDt);      break
        case 'flying_off': this.tickFlyingOff(bird, i, stepDt);  break
      }
    }
  }

  destroy(): void {
    for (const bird of this.birds) bird.entity.destroy()
    this.birds = []
    this.root.destroy()
  }

  // ─── State Handlers ────────────────────────────────────────────────────────

  private tickIdle(bird: GardenBirdEntry, idx: number, dt: number): void {
    bird.timer -= dt
    if (bird.timer > 0 || this.perches.length === 0) return

    // Pick a random repo tree as perch
    const perch = this.perches[Math.floor(Math.random() * this.perches.length)]
    bird.perchTarget.set(perch.x, perch.y + PERCH_Y_ABOVE[idx % PERCH_Y_ABOVE.length], perch.z)

    // Approach waypoint: directly above the final perch
    bird.target.set(bird.perchTarget.x, bird.perchTarget.y + APPROACH_ABOVE, bird.perchTarget.z)

    // Start from a random distant entry point
    const θ = Math.random() * Math.PI * 2
    bird.pos.set(Math.sin(θ) * SPAWN_RADIUS, SPAWN_Y, Math.cos(θ) * SPAWN_RADIUS)
    bird.entity.setPosition(bird.pos.x, bird.pos.y, bird.pos.z)
    bird.entity.enabled = true
    bird.state = 'approach'
  }

  private tickApproach(bird: GardenBirdEntry, dt: number): void {
    this.seekTarget(bird, FLIGHT_SPEED, dt)
    this.orientTowardTarget(bird)
    this.flapWings(bird, FLAP_FLIGHT_HZ, FLAP_FLIGHT_AMP)

    if (this.distToTarget(bird) < APPROACH_DIST) {
      // Arrived above perch — start slow descent
      bird.target.copy(bird.perchTarget)
      bird.state = 'landing'
    }
  }

  private tickLanding(bird: GardenBirdEntry, dt: number): void {
    this.seekTarget(bird, LAND_SPEED, dt)
    this.orientTowardTarget(bird)

    // Wing-tuck: interpolate amplitude from full to perch as we descend
    const t = Math.min(1, this.distToTarget(bird) / APPROACH_ABOVE)
    const amp = FLAP_PERCH_AMP + (FLAP_FLIGHT_AMP - FLAP_PERCH_AMP) * t
    this.flapWings(bird, FLAP_FLIGHT_HZ, amp)

    if (this.distToTarget(bird) < PERCH_DIST) {
      bird.pos.copy(bird.perchTarget)
      bird.entity.setPosition(bird.pos.x, bird.pos.y, bird.pos.z)
      bird.timer = PERCH_TIME_MIN + Math.random() * (PERCH_TIME_MAX - PERCH_TIME_MIN)
      bird.state = 'perching'
    }
  }

  private tickPerching(bird: GardenBirdEntry, dt: number): void {
    bird.timer -= dt
    this.flapWings(bird, FLAP_PERCH_HZ, FLAP_PERCH_AMP)

    if (bird.timer <= 0) {
      // Pick random exit point far away
      const θ = Math.random() * Math.PI * 2
      bird.target.set(Math.sin(θ) * SPAWN_RADIUS, SPAWN_Y, Math.cos(θ) * SPAWN_RADIUS)
      bird.state = 'flying_off'
    }
  }

  private tickFlyingOff(bird: GardenBirdEntry, _idx: number, dt: number): void {
    this.seekTarget(bird, FLIGHT_SPEED, dt)
    this.orientTowardTarget(bird)
    this.flapWings(bird, FLAP_FLIGHT_HZ, FLAP_FLIGHT_AMP)

    // Hide once far enough from scene center
    const d = Math.sqrt(bird.pos.x * bird.pos.x + bird.pos.z * bird.pos.z)
    if (d > EXIT_RADIUS) {
      bird.entity.enabled = false
      bird.timer = IDLE_TIME_MIN + Math.random() * (IDLE_TIME_MAX - IDLE_TIME_MIN)
      bird.state = 'idle'
    }
  }

  // ─── Motion Helpers ────────────────────────────────────────────────────────

  /** Move pos toward target at given speed. Updates entity position. */
  private seekTarget(bird: GardenBirdEntry, speed: number, dt: number): void {
    this._diff.sub2(bird.target, bird.pos)
    const dist = this._diff.length()
    if (dist < 0.001) return
    const step = Math.min(speed * dt, dist)
    bird.pos.x += (this._diff.x / dist) * step
    bird.pos.y += (this._diff.y / dist) * step
    bird.pos.z += (this._diff.z / dist) * step
    bird.entity.setPosition(bird.pos.x, bird.pos.y, bird.pos.z)
  }

  /** Orient entity to face its current target. */
  private orientTowardTarget(bird: GardenBirdEntry): void {
    this._diff.sub2(bird.target, bird.pos)
    if (this._diff.length() < 0.01) return
    bird.entity.lookAt(bird.target)
    bird.entity.rotateLocal(0, MODEL_YAW, 0)
  }

  private distToTarget(bird: GardenBirdEntry): number {
    this._diff.sub2(bird.target, bird.pos)
    return this._diff.length()
  }

  /** Procedural wing flap — same pattern as BirdSystem.ts. */
  private flapWings(bird: GardenBirdEntry, hz: number, amp: number): void {
    const flap = Math.sin(bird.elapsed * hz * Math.PI * 2 + bird.flapPhase) * amp
    bird.wingL?.setLocalEulerAngles( flap, 0, 0)
    bird.wingR?.setLocalEulerAngles(-flap, 0, 0)
  }
}
