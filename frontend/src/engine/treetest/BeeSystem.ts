/**
 * BeeSystem — 5 bees with random waypoint navigation around the tree canopy.
 *
 * Independent, reusable component. Attach to any tree via setTreeTarget().
 *
 * Animation: purely procedural — no PlayCanvas anim/animation component.
 *   - Wing flap: per-frame setLocalEulerAngles on wing-left / wing-right nodes
 *   - Vertical buzz: high-frequency sin wave on Y position
 *
 * Why no anim component: see BirdSystem.ts for the reason. Adding an anim
 * component to instantiateRenderEntity() roots causes GL state corruption
 * when destroyed mid-frame.
 *
 * Motion:
 *   - Random waypoint navigation within the canopy sphere
 *   - Arrive: decelerate within SLOW_RADIUS of each waypoint
 *   - Smooth yaw: lerp toward travel direction instead of snap lookAt
 *
 * Reuse: setTreeTarget(center, radius, height) works for any tree.
 */
import * as pc from 'playcanvas'
import { AssetLoader } from '../assets/AssetLoader'

const GLB_PATH       = 'assets/garden/animal-bee.glb'
const BEE_COUNT      = 5
const BEE_SCALE      = 0.30

const BEE_SPEED      = 2.2    // world units / sec (max)
const ARRIVAL_DIST   = 0.4
const SLOW_RADIUS    = 1.5    // arrive deceleration zone
const MIN_SPEED_FRAC = 0.15   // speed floor — bees never fully stop

const TURN_RATE        = 200  // degrees / sec for smooth yaw lerp
const MODEL_YAW_OFFSET = 0

const FLAP_FREQ      = 20     // Hz — fast insect wingbeat
const FLAP_AMP_DEG   = 40     // degrees

const BUZZ_FREQ      = 14     // Hz — vertical body buzz
const BUZZ_AMP       = 0.05   // world units

interface BeeEntry {
  entity:       pc.Entity
  wingL:        pc.GraphNode | null
  wingR:        pc.GraphNode | null
  pos:          pc.Vec3
  target:       pc.Vec3
  currentYaw:   number
  buzzPhase:    number
  buzzFreqMult: number
  flapPhase:    number
}

export class BeeSystem {
  private loader: AssetLoader
  private root:   pc.Entity
  private bees:   BeeEntry[] = []
  private asset:  pc.Asset | null = null

  private center = new pc.Vec3(0, 5, 0)
  private radius = 3
  private active = false
  private time   = 0

  private _dir = new pc.Vec3()

  constructor(app: pc.AppBase) {
    this.loader = new AssetLoader(app)
    this.root   = new pc.Entity('BeeRoot')
    app.root.addChild(this.root)
  }

  async init(): Promise<void> {
    try {
      this.asset = await this.loader.load(GLB_PATH)
    } catch (e) {
      console.warn('[BeeSystem] Failed to load bee GLB — bees disabled.', e)
    }
  }

  setTreeTarget(center: pc.Vec3, radius: number, height: number): void {
    this.center.set(center.x, height, center.z)
    this.radius = Math.max(radius, 1.0)
    this.spawnBees()
    this.active = true
  }

  update(dt: number): void {
    if (!this.active || this.bees.length === 0) return
    this.time += dt

    for (const bee of this.bees) {
      this._dir.sub2(bee.target, bee.pos)
      const dist = this._dir.length()

      if (dist < ARRIVAL_DIST) {
        this.randomTarget(bee.target)
      } else {
        const speedFrac = Math.min(dist / SLOW_RADIUS, 1.0)
        const speed     = BEE_SPEED * Math.max(speedFrac, MIN_SPEED_FRAC)
        bee.pos.x += (this._dir.x / dist) * speed * dt
        bee.pos.y += (this._dir.y / dist) * speed * dt
        bee.pos.z += (this._dir.z / dist) * speed * dt

        const targetYaw = Math.atan2(this._dir.x, this._dir.z) * (180 / Math.PI) + MODEL_YAW_OFFSET
        bee.currentYaw  = lerpAngle(bee.currentYaw, targetYaw, TURN_RATE * dt)
      }

      const buzz = Math.sin(this.time * BUZZ_FREQ * bee.buzzFreqMult + bee.buzzPhase) * BUZZ_AMP
      bee.entity.setPosition(bee.pos.x, bee.pos.y + buzz, bee.pos.z)
      bee.entity.setEulerAngles(0, bee.currentYaw, 0)

      this.flapWings(bee)
    }
  }

  /** Toggle visibility without destroying — preserves spawn state for re-enable. */
  setEnabled(enabled: boolean): void {
    this.active       = enabled && this.bees.length > 0
    this.root.enabled = enabled
  }

  clear(): void {
    for (const bee of this.bees) bee.entity.destroy()
    this.bees   = []
    this.active = false
  }

  destroy(): void {
    this.clear()
    this.root.destroy()
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  private spawnBees(): void {
    this.clear()
    if (!this.asset) return

    for (let i = 0; i < BEE_COUNT; i++) {
      const entity = this.loader.instance(this.asset)
      entity.setLocalScale(BEE_SCALE, BEE_SCALE, BEE_SCALE)
      this.root.addChild(entity)

      const startPos = new pc.Vec3()
      const target   = new pc.Vec3()
      this.randomTarget(startPos)
      this.randomTarget(target)
      entity.setPosition(startPos.x, startPos.y, startPos.z)

      this.bees.push({
        entity,
        wingL:        entity.findByName('wing-left')  ?? null,
        wingR:        entity.findByName('wing-right') ?? null,
        pos:          startPos.clone(),
        target,
        currentYaw:   Math.random() * 360,
        buzzPhase:    Math.random() * Math.PI * 2,
        buzzFreqMult: 0.75 + Math.random() * 0.5,
        flapPhase:    Math.random() * Math.PI * 2,
      })
    }
  }

  private flapWings(bee: BeeEntry): void {
    const flap = Math.sin(this.time * FLAP_FREQ * Math.PI * 2 + bee.flapPhase) * FLAP_AMP_DEG
    bee.wingL?.setLocalEulerAngles( flap, 0, 0)
    bee.wingR?.setLocalEulerAngles(-flap, 0, 0)
  }

  /**
   * Random point in the canopy sphere.
   * cbrt(random) gives uniform sphere volume — avoids clustering near center.
   */
  private randomTarget(out: pc.Vec3): void {
    const theta = Math.random() * Math.PI * 2
    const phi   = Math.acos(2 * Math.random() - 1)
    const r     = this.radius * Math.cbrt(Math.random())
    out.set(
      this.center.x + r * Math.sin(phi) * Math.cos(theta),
      this.center.y + (Math.random() - 0.4) * this.radius * 0.7,
      this.center.z + r * Math.sin(phi) * Math.sin(theta),
    )
  }
}

/** Lerp angles (degrees) via shortest arc — prevents wrap-around spinning. */
function lerpAngle(current: number, target: number, maxDelta: number): number {
  const diff = ((target - current + 540) % 360) - 180
  if (Math.abs(diff) <= maxDelta) return target
  return current + Math.sign(diff) * maxDelta
}
