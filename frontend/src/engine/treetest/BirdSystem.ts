/**
 * BirdSystem — 3 parrots orbiting the tree canopy.
 *
 * Independent, reusable component. Attach to any tree via setTreeTarget().
 *
 * Animation: purely procedural — no PlayCanvas anim/animation component.
 *   - Wing flap: per-frame setLocalEulerAngles on wing-left / wing-right nodes
 *   - Body bob: sin-wave Y offset baked into the orbit position
 *   - Banking: roll applied after lookAt
 *
 * Why no anim component: adding pc.AnimComponent directly to an
 * instantiateRenderEntity() root causes mid-frame GL state corruption when
 * the entity is destroyed (entity.destroy() defers GPU cleanup to end-of-frame
 * but leaf draw calls happen first). The safe pattern (wrapper entity + anim
 * on wrapper + render entity as child) is reserved for CharacterFactory where
 * skinned animations justify the complexity.
 *
 * Motion:
 *   - Base circular orbit at different radii / heights / speeds
 *   - Per-bird wander angle drifts the orbit (no perfect circles)
 *   - Pairwise separation keeps birds from overlapping
 *
 * Reuse: setTreeTarget(center, radius, height) works for any tree.
 */
import * as pc from 'playcanvas'
import { AssetLoader } from '../assets/AssetLoader'

const GLB_PATH          = 'assets/garden/animal-parrot.glb'
const BIRD_COUNT        = 3
const BIRD_SCALE        = 0.6

const BASE_ORBIT_SPEED  = 0.4   // rad/s
const BANK_DEGREES      = 22
const MODEL_YAW_OFFSET  = 180   // GLB faces +Z; orbit math uses -Z convention

const FLAP_FREQ         = 4.5   // Hz
const FLAP_AMP_DEG      = 32    // degrees

const WANDER_RATE       = 0.45  // rad/s max drift
const WANDER_RADIUS     = 0.9   // world units

const SEP_RADIUS        = 2.2   // world units — pairwise repulsion threshold
const SEP_STRENGTH      = 1.8   // units per second

const ORBIT_CONFIGS: ReadonlyArray<{
  radiusAdd: number; heightAdd: number; speedMult: number; phase: number
}> = [
  { radiusAdd:  0.0, heightAdd: 0.0, speedMult:  1.0, phase: 0.0 },
  { radiusAdd:  0.9, heightAdd: 1.5, speedMult:  0.8, phase: 2.1 },
  { radiusAdd: -0.6, heightAdd: 2.5, speedMult: -1.3, phase: 4.2 },
]

interface BirdEntry {
  entity:      pc.Entity
  // GraphNode returned by findByName; setLocalEulerAngles lives on GraphNode
  wingL:       pc.GraphNode | null
  wingR:       pc.GraphNode | null
  angle:       number
  speed:       number
  orbitR:      number
  orbitH:      number
  bobPhase:    number
  flapPhase:   number
  wanderAngle: number
  wx:          number
  wz:          number
}

export class BirdSystem {
  private loader: AssetLoader
  private root:   pc.Entity
  private birds:  BirdEntry[] = []
  private asset:  pc.Asset | null = null

  private center     = new pc.Vec3(0, 6, 0)
  private baseRadius = 4
  private active     = false
  private time       = 0

  private _lookAt = new pc.Vec3()

  constructor(app: pc.AppBase) {
    this.loader = new AssetLoader(app)
    this.root   = new pc.Entity('BirdRoot')
    app.root.addChild(this.root)
  }

  async init(): Promise<void> {
    try {
      this.asset = await this.loader.load(GLB_PATH)
    } catch (e) {
      console.warn('[BirdSystem] Failed to load parrot GLB — birds disabled.', e)
    }
  }

  setTreeTarget(center: pc.Vec3, radius: number, height: number): void {
    this.center.copy(center)
    this.baseRadius = radius
    this.spawnBirds(height)
    this.active = true
  }

  update(dt: number): void {
    if (!this.active || this.birds.length === 0) return
    this.time += dt

    for (const bird of this.birds) {
      bird.angle       += bird.speed * dt
      bird.wanderAngle += (Math.random() - 0.5) * WANDER_RATE * dt
      bird.wx           = Math.sin(bird.wanderAngle) * WANDER_RADIUS
      bird.wz           = Math.cos(bird.wanderAngle) * WANDER_RADIUS
    }

    // Pairwise separation — O(n²) is negligible for 3 birds
    for (let i = 0; i < this.birds.length; i++) {
      for (let j = i + 1; j < this.birds.length; j++) {
        const a = this.birds[i], b = this.birds[j]
        const dx = a.wx - b.wx, dz = a.wz - b.wz
        const dist = Math.sqrt(dx * dx + dz * dz + 0.0001)
        if (dist < SEP_RADIUS) {
          const push = SEP_STRENGTH * dt * (1 - dist / SEP_RADIUS)
          a.wx += (dx / dist) * push; a.wz += (dz / dist) * push
          b.wx -= (dx / dist) * push; b.wz -= (dz / dist) * push
        }
      }
    }

    for (const bird of this.birds) {
      const bob = Math.sin(this.time * 0.7 + bird.bobPhase) * 0.35
      const x   = this.center.x + bird.orbitR * Math.sin(bird.angle) + bird.wx
      const y   = bird.orbitH   + bob
      const z   = this.center.z + bird.orbitR * Math.cos(bird.angle) + bird.wz
      bird.entity.setPosition(x, y, z)
      this.orientBird(bird, x, y, z)
      this.flapWings(bird)
    }
  }

  /** Toggle visibility without destroying — preserves spawn state for re-enable. */
  setEnabled(enabled: boolean): void {
    this.active       = enabled && this.birds.length > 0
    this.root.enabled = enabled
  }

  clear(): void {
    for (const bird of this.birds) bird.entity.destroy()
    this.birds  = []
    this.active = false
  }

  destroy(): void {
    this.clear()
    this.root.destroy()
  }

  // ─── Private ──────────────────────────────────────────────────────────────

  private spawnBirds(height: number): void {
    this.clear()
    if (!this.asset) return

    for (let i = 0; i < BIRD_COUNT; i++) {
      const cfg    = ORBIT_CONFIGS[i]
      const entity = this.loader.instance(this.asset)
      entity.setLocalScale(BIRD_SCALE, BIRD_SCALE, BIRD_SCALE)
      this.root.addChild(entity)

      this.birds.push({
        entity,
        wingL:       entity.findByName('wing-left')  ?? null,
        wingR:       entity.findByName('wing-right') ?? null,
        angle:       cfg.phase,
        speed:       BASE_ORBIT_SPEED * cfg.speedMult,
        orbitR:      this.baseRadius + cfg.radiusAdd,
        orbitH:      height + cfg.heightAdd,
        bobPhase:    Math.random() * Math.PI * 2,
        flapPhase:   Math.random() * Math.PI * 2,
        wanderAngle: Math.random() * Math.PI * 2,
        wx: 0,
        wz: 0,
      })
    }
  }

  private orientBird(bird: BirdEntry, bx: number, by: number, bz: number): void {
    const sign = bird.speed >= 0 ? 1 : -1
    const tx   = Math.cos(bird.angle) * sign
    const tz   = -Math.sin(bird.angle) * sign
    this._lookAt.set(bx + tx, by, bz + tz)
    bird.entity.lookAt(this._lookAt)
    const bankSign = bird.speed >= 0 ? -1 : 1
    bird.entity.rotateLocal(0, MODEL_YAW_OFFSET, BANK_DEGREES * bankSign)
  }

  private flapWings(bird: BirdEntry): void {
    const flap = Math.sin(this.time * FLAP_FREQ * Math.PI * 2 + bird.flapPhase) * FLAP_AMP_DEG
    bird.wingL?.setLocalEulerAngles( flap, 0, 0)
    bird.wingR?.setLocalEulerAngles(-flap, 0, 0)
  }
}
