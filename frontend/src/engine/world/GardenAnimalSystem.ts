// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * GardenAnimalSystem — Cube-pet animals wandering the garden on foot.
 *
 * Follows the GardenBirdSystem pattern:
 *   - loader.instance() for GLB cloning
 *   - findByName() for body part nodes
 *   - Procedural sine-wave animation (no AnimComponent)
 *
 * Kenney cube-pets have these named nodes:
 *   body, head, leg-front-left, leg-front-right, leg-back-left, leg-back-right, tail
 *
 * FSM: idle → walking → (eating | looking | resting) → walking → …
 *
 * Behaviors during rest:
 *   - eating:  head bobs down toward ground repeatedly
 *   - looking: head turns left and right (curious)
 *   - resting: gentle body breathing + idle tail wag
 */
import * as pc from 'playcanvas'
import { AssetLoader } from '../assets/AssetLoader'
import { ANIMALS } from '../assets/AssetManifest'
import { randRange } from '../utils/MathUtils'

const ANIMAL_SCALE = 0.35
const WALK_SPEED = 1.2
const WANDER_RADIUS = 28
const REST_TIME_MIN = 3
const REST_TIME_MAX = 8
const IDLE_DELAY_MAX = 6
const ARRIVE_DIST = 0.5

// Walk animation
const WALK_LEG_HZ = 3.0
const WALK_LEG_AMP = 25
const WALK_BODY_BOB_HZ = 6.0    // body bounces at double leg freq
const WALK_BODY_BOB_AMP = 0.02  // subtle Y bounce (world units)

// Tail wag
const TAIL_WALK_HZ = 2.5
const TAIL_WALK_AMP = 18
const TAIL_IDLE_HZ = 1.0
const TAIL_IDLE_AMP = 8

// Eating animation (head bobs down)
const EAT_HZ = 0.8
const EAT_AMP = 30              // degrees — head pitch down

// Looking animation (head turns side to side)
const LOOK_HZ = 0.4
const LOOK_AMP = 40             // degrees — head yaw left/right

// Idle breathing (gentle body scale pulse)
const BREATHE_HZ = 0.6
const BREATHE_AMP = 0.008       // very subtle scale pulse

type AnimalState = 'idle' | 'walking' | 'eating' | 'looking' | 'resting'

interface AnimalEntry {
  entity: pc.Entity
  // Body part nodes for procedural animation
  body:  pc.GraphNode | null
  head:  pc.GraphNode | null
  legFL: pc.GraphNode | null
  legFR: pc.GraphNode | null
  legBL: pc.GraphNode | null
  legBR: pc.GraphNode | null
  tail:  pc.GraphNode | null
  pos: pc.Vec3
  target: pc.Vec3
  state: AnimalState
  timer: number
  speed: number
  elapsed: number
  phase: number
  scale: number                 // cached scale for breathing pulse
}

const ANIMAL_GLBS = Object.values(ANIMALS)

// Rest behaviors to randomly choose from
const REST_BEHAVIORS: AnimalState[] = ['eating', 'looking', 'resting']

export class GardenAnimalSystem {
  private root: pc.Entity
  private animals: AnimalEntry[] = []
  private updateAccum = 0   // dt accumulator — system ticks at 30Hz, not 60
  private static readonly _diff = new pc.Vec3()

  constructor(app: pc.AppBase) {
    this.root = new pc.Entity('GardenAnimals')
    app.root.addChild(this.root)
  }

  async init(loader: AssetLoader): Promise<void> {
    for (let i = 0; i < ANIMAL_GLBS.length; i++) {
      try {
        const asset = await loader.load(ANIMAL_GLBS[i])
        const entity = loader.instance(asset)

        const scale = ANIMAL_SCALE * randRange(0.85, 1.15)
        entity.setLocalScale(scale, scale, scale)
        entity.enabled = false

        entity.forEach((node: pc.GraphNode) => {
          const e = node as pc.Entity
          if (e.render) {
            e.render.castShadows = false
            e.render.receiveShadows = false
          }
        })

        this.root.addChild(entity)

        const startX = randRange(-WANDER_RADIUS * 0.5, WANDER_RADIUS * 0.5)
        const startZ = randRange(-WANDER_RADIUS * 0.5, WANDER_RADIUS * 0.5)

        this.animals.push({
          entity,
          body:  entity.findByName('body')             ?? null,
          head:  entity.findByName('head')             ?? null,
          legFL: entity.findByName('leg-front-left')   ?? null,
          legFR: entity.findByName('leg-front-right')  ?? null,
          legBL: entity.findByName('leg-back-left')    ?? null,
          legBR: entity.findByName('leg-back-right')   ?? null,
          tail:  entity.findByName('tail')             ?? null,
          pos: new pc.Vec3(startX, 0, startZ),
          target: new pc.Vec3(startX, 0, startZ),
          state: 'idle',
          timer: randRange(1, IDLE_DELAY_MAX),
          speed: WALK_SPEED * randRange(0.7, 1.3),
          elapsed: 0,
          phase: Math.random() * Math.PI * 2,
          scale,
        })
      } catch (err) {
        console.warn(`[GardenAnimalSystem] Failed to load ${ANIMAL_GLBS[i]}:`, err)
      }
    }
  }

  update(dt: number): void {
    // 30Hz throttle. State handlers consume dt linearly (timer -= dt,
    // pos += speed*dt) so accumulated dt every other frame is equivalent.
    // 30Hz keeps walking/head-bob motion visibly smooth at orchard scale.
    this.updateAccum += dt
    if (this.updateAccum < 1 / 30) return
    const stepDt = this.updateAccum
    this.updateAccum = 0

    for (const animal of this.animals) {
      animal.elapsed += stepDt
      switch (animal.state) {
        case 'idle':    this.tickIdle(animal, stepDt); break
        case 'walking': this.tickWalking(animal, stepDt); break
        case 'eating':  this.tickEating(animal, stepDt); break
        case 'looking': this.tickLooking(animal, stepDt); break
        case 'resting': this.tickResting(animal, stepDt); break
      }
    }
  }

  destroy(): void {
    this.root.destroy()
    this.animals = []
  }

  // ─── State handlers ───────────────────────────────────────────────────────

  private tickIdle(animal: AnimalEntry, dt: number): void {
    animal.timer -= dt
    if (animal.timer <= 0) {
      animal.entity.enabled = true
      animal.entity.setPosition(animal.pos.x, 0, animal.pos.z)
      this.pickNewTarget(animal)
      animal.state = 'walking'
    }
  }

  private tickWalking(animal: AnimalEntry, dt: number): void {
    GardenAnimalSystem._diff.sub2(animal.target, animal.pos)
    GardenAnimalSystem._diff.y = 0
    const dist = GardenAnimalSystem._diff.length()

    if (dist < ARRIVE_DIST) {
      // Pick a random rest behavior
      animal.state = REST_BEHAVIORS[Math.floor(Math.random() * REST_BEHAVIORS.length)]
      animal.timer = randRange(REST_TIME_MIN, REST_TIME_MAX)
      // Reset head/body to neutral on state change
      animal.head?.setLocalEulerAngles(0, 0, 0)
      return
    }

    const step = Math.min(animal.speed * dt, dist)
    animal.pos.x += (GardenAnimalSystem._diff.x / dist) * step
    animal.pos.z += (GardenAnimalSystem._diff.z / dist) * step
    animal.pos.y = 0

    // Body bob while walking
    const bob = Math.abs(Math.sin(animal.elapsed * WALK_BODY_BOB_HZ * Math.PI * 2 + animal.phase)) * WALK_BODY_BOB_AMP
    animal.entity.setPosition(animal.pos.x, bob, animal.pos.z)

    // Face movement direction
    if (dist > 0.1) {
      animal.entity.lookAt(animal.target.x, 0, animal.target.z)
      animal.entity.rotateLocal(0, 180, 0)
    }

    this.animateLegs(animal, WALK_LEG_HZ, WALK_LEG_AMP)
    this.animateTail(animal, TAIL_WALK_HZ, TAIL_WALK_AMP)
  }

  /** Eating: head bobs down repeatedly (like pecking at grass). */
  private tickEating(animal: AnimalEntry, dt: number): void {
    animal.timer -= dt

    const headPitch = Math.abs(Math.sin(animal.elapsed * EAT_HZ * Math.PI * 2 + animal.phase)) * EAT_AMP
    animal.head?.setLocalEulerAngles(headPitch, 0, 0)

    // Legs still, tail slow wag
    this.animateLegs(animal, 0, 0)
    this.animateTail(animal, TAIL_IDLE_HZ, TAIL_IDLE_AMP)
    this.animateBreathe(animal)

    if (animal.timer <= 0) {
      animal.head?.setLocalEulerAngles(0, 0, 0)
      this.pickNewTarget(animal)
      animal.state = 'walking'
    }
  }

  /** Looking: head turns left and right (curious, surveying). */
  private tickLooking(animal: AnimalEntry, dt: number): void {
    animal.timer -= dt

    const headYaw = Math.sin(animal.elapsed * LOOK_HZ * Math.PI * 2 + animal.phase) * LOOK_AMP
    animal.head?.setLocalEulerAngles(0, headYaw, 0)

    this.animateLegs(animal, 0, 0)
    this.animateTail(animal, TAIL_IDLE_HZ * 1.5, TAIL_IDLE_AMP * 1.5)
    this.animateBreathe(animal)

    if (animal.timer <= 0) {
      animal.head?.setLocalEulerAngles(0, 0, 0)
      this.pickNewTarget(animal)
      animal.state = 'walking'
    }
  }

  /** Resting: stands still with gentle breathing and idle tail wag. */
  private tickResting(animal: AnimalEntry, dt: number): void {
    animal.timer -= dt

    this.animateLegs(animal, 0, 0)
    this.animateTail(animal, TAIL_IDLE_HZ, TAIL_IDLE_AMP)
    this.animateBreathe(animal)

    if (animal.timer <= 0) {
      this.pickNewTarget(animal)
      animal.state = 'walking'
    }
  }

  // ─── Procedural animation ─────────────────────────────────────────────────

  /** Diagonal gait: FL+BR swing together, FR+BL opposite. */
  private animateLegs(animal: AnimalEntry, hz: number, amp: number): void {
    if (amp === 0) {
      // Reset legs to neutral
      animal.legFL?.setLocalEulerAngles(0, 0, 0)
      animal.legFR?.setLocalEulerAngles(0, 0, 0)
      animal.legBL?.setLocalEulerAngles(0, 0, 0)
      animal.legBR?.setLocalEulerAngles(0, 0, 0)
      return
    }
    const t = animal.elapsed * hz * Math.PI * 2 + animal.phase
    const swing = Math.sin(t) * amp
    animal.legFL?.setLocalEulerAngles(swing, 0, 0)
    animal.legBR?.setLocalEulerAngles(swing, 0, 0)
    animal.legFR?.setLocalEulerAngles(-swing, 0, 0)
    animal.legBL?.setLocalEulerAngles(-swing, 0, 0)
  }

  /** Tail wag side-to-side. */
  private animateTail(animal: AnimalEntry, hz: number, amp: number): void {
    const wag = Math.sin(animal.elapsed * hz * Math.PI * 2 + animal.phase * 1.7) * amp
    animal.tail?.setLocalEulerAngles(0, wag, 0)
  }

  /** Subtle breathing — gentle body scale pulse. */
  private animateBreathe(animal: AnimalEntry): void {
    const pulse = Math.sin(animal.elapsed * BREATHE_HZ * Math.PI * 2 + animal.phase) * BREATHE_AMP
    const s = animal.scale + pulse
    animal.entity.setLocalScale(s, s, s)
  }

  // ─── Helpers ──────────────────────────────────────────────────────────────

  private pickNewTarget(animal: AnimalEntry): void {
    const angle = Math.random() * Math.PI * 2
    const dist = randRange(5, 15)
    let tx = animal.pos.x + Math.cos(angle) * dist
    let tz = animal.pos.z + Math.sin(angle) * dist

    const r = Math.sqrt(tx * tx + tz * tz)
    if (r > WANDER_RADIUS) {
      tx = (tx / r) * WANDER_RADIUS
      tz = (tz / r) * WANDER_RADIUS
    }
    animal.target.set(tx, 0, tz)
  }
}
