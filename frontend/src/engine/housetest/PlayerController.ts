/**
 * PlayerController — keyboard-driven Kenney character with AABB collision.
 *
 * Loads a Kenney Blocky Character GLB, drives idle↔walk animations via
 * PlayCanvas AnimComponent, and moves using WASD with AABB slide collision.
 *
 * Entity hierarchy (same wrapper pattern as CharacterFactory):
 *   playerWrapper (positioned in world)
 *     └── renderEntity (skinned GLB, scaled + offset so feet sit at Y=0)
 *         AnimComponent lives on the wrapper (auto-discovers skinned children)
 *
 * Note: Using setPosition() directly (no rigidbody). When integrating into
 * the main dashboard, swap to Dynamic RigidBody + applyForce() with Ammo.js
 * for proper physics collision.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { InputManager } from '../input/InputManager'
import { getCharacterGLB } from '../assets/AssetManifest'
import { parseCharacterModel, isKayKitConfig } from '../characters/CharacterConfig'
import { KayKitCharacterFactory } from '../characters/KayKitCharacterFactory'
import { CharacterFactory } from '../characters/CharacterFactory'
import { type ContainerWithAnims, findAnimTrack } from '../characters/AnimUtils'
import { tryMove, type CollisionBox } from './CollisionSystem'

// ─── Character model constants (matches CharacterFactory) ────
const CHAR_NATIVE_HEIGHT = 9.0
const CHAR_TARGET_HEIGHT = 1.0
const CHAR_SCALE = CHAR_TARGET_HEIGHT / CHAR_NATIVE_HEIGHT
/** Lifts model feet (Y≈-1 native) to Y=0 in wrapper space. */
const CHAR_Y_OFFSET = 1.0 * CHAR_SCALE

// ─── Movement constants ──────────────────────────────────────
const MOVE_SPEED = 3.0  // world units per second

// ─── Animation state graph ──────────────────────────────────
// Extended from LOCOMOTION_STATE_GRAPH (AnimUtils.ts) with Sleep state for house interiors.
// NOTE: uses INTEGER parameters (sitting=0/1, sleeping=0/1) vs BOOLEAN in LOCOMOTION_STATE_GRAPH.
// This is intentional — the house interior needs integer tri-state (idle/sit/sleep) logic.
// KayKit characters in houses use their own factory animations (Sit_Chair_Idle, Lie_Idle).
const STATE_GRAPH = {
  layers: [{
    name: 'locomotion',
    states: [
      { name: 'START' },
      { name: 'Idle',  speed: 1.0 },
      { name: 'Walk',  speed: 1.0 },
      { name: 'Sit',   speed: 1.0 },
      { name: 'Sleep', speed: 1.0 },
    ],
    transitions: [
      { from: 'START', to: 'Idle', time: 0, priority: 0 },
      {
        from: 'Idle', to: 'Walk', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_GREATER_THAN, value: 0 }],
      },
      {
        from: 'Walk', to: 'Idle', time: 0, priority: 0,
        conditions: [{ parameterName: 'speed', predicate: pc.ANIM_LESS_THAN_EQUAL_TO, value: 0 }],
      },
      {
        from: 'Idle', to: 'Sit', time: 0.2, priority: 1,
        conditions: [{ parameterName: 'sitting', predicate: pc.ANIM_EQUAL_TO, value: 1 }],
      },
      {
        from: 'Sit', to: 'Idle', time: 0.2, priority: 0,
        conditions: [{ parameterName: 'sitting', predicate: pc.ANIM_EQUAL_TO, value: 0 }],
      },
      {
        from: 'Idle', to: 'Sleep', time: 0.3, priority: 1,
        conditions: [{ parameterName: 'sleeping', predicate: pc.ANIM_EQUAL_TO, value: 1 }],
      },
      {
        from: 'Sleep', to: 'Idle', time: 0.3, priority: 0,
        conditions: [{ parameterName: 'sleeping', predicate: pc.ANIM_EQUAL_TO, value: 0 }],
      },
    ],
  }],
  parameters: {
    speed:    { name: 'speed',    type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    sitting:  { name: 'sitting',  type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    sleeping: { name: 'sleeping', type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
  },
}

// ContainerWithAnims and findAnimTrack imported from shared AnimUtils

export class PlayerController {
  private loader: AssetLoader
  private input: InputManager
  private entity: pc.Entity | null = null
  private collisionBoxes: CollisionBox[] = []
  private _sitting  = false
  private _sleeping = false

  // Scratch Vec3s — avoids allocation in update loop
  private readonly _dir  = new pc.Vec3()
  private readonly _next = new pc.Vec3()

  get isSitting():  boolean { return this._sitting  }
  get isSleeping(): boolean { return this._sleeping }

  constructor(loader: AssetLoader, input: InputManager) {
    this.loader = loader
    this.input = input
  }

  // +Z-native model at yaw=0 faces +Z (toward camera). 180° = face toward house (-Z).
  static readonly SPAWN_YAW = 180

  async init(root: pc.Entity, startX: number, startZ: number, characterModel?: string | null): Promise<pc.Entity> {
    const config = parseCharacterModel(characterModel ?? null)

    if (isKayKitConfig(config)) {
      // KayKit character — use factory to create entity with animations + colors
      const factory = new KayKitCharacterFactory(this.loader)
      const result = await factory.create(
        'player', '', config,
        startX, 0, startZ,
        PlayerController.SPAWN_YAW, false,
      )
      // Remove the name label (not needed for local player in house)
      const label = result.entity.findByTag('billboard')[0] as pc.Entity | undefined
      if (label) label.destroy()

      // Scale down for interior — garden scale (0.95) is too large for the small room
      const interiorScale = 0.75
      const renderChild = result.entity.children[0]
      if (renderChild) {
        const s = renderChild.getLocalScale()
        renderChild.setLocalScale(s.x * interiorScale, s.y * interiorScale, s.z * interiorScale)
      }

      root.addChild(result.entity)
      this.entity = result.entity
      return result.entity
    }

    // Legacy Kenney Blocky character path
    const variant = config.characterId || CharacterFactory.getVariant('player', null)
    const glbPath = getCharacterGLB(variant)
    const asset = await this.loader.load(glbPath)
    const container = asset.resource as ContainerWithAnims

    const wrapper = new pc.Entity('Player')
    wrapper.setPosition(startX, 0, startZ)
    wrapper.setEulerAngles(0, PlayerController.SPAWN_YAW, 0)

    // Render entity — skinned GLB, offset so feet sit at Y=0
    const renderEntity = container.instantiateRenderEntity()
    renderEntity.setLocalScale(CHAR_SCALE, CHAR_SCALE, CHAR_SCALE)
    renderEntity.setLocalPosition(0, CHAR_Y_OFFSET, 0)
    wrapper.addChild(renderEntity)

    // Anim component — discovers skinned mesh in child automatically
    wrapper.addComponent('anim', { activate: true })
    wrapper.anim!.loadStateGraph(STATE_GRAPH)
    const layer = wrapper.anim!.baseLayer
    if (layer) {
      const idle = findAnimTrack(container, 'idle')
      const walk = findAnimTrack(container, 'walk')
      // Fallback chain: try common keyword variants, then fall back to idle.
      const sit   = findAnimTrack(container, 'sit')   ?? idle
      const sleep = findAnimTrack(container, 'sleep') ?? findAnimTrack(container, 'lie') ?? findAnimTrack(container, 'death') ?? idle
      if (idle)  layer.assignAnimation('Idle',  idle)
      if (walk)  layer.assignAnimation('Walk',  walk)
      if (sit)   layer.assignAnimation('Sit',   sit)
      if (sleep) layer.assignAnimation('Sleep', sleep)
    }

    root.addChild(wrapper)
    this.entity = wrapper
    return wrapper
  }

  /** Swap collision boxes when transitioning between scenes. */
  setCollisionBoxes(boxes: CollisionBox[]): void {
    this.collisionBoxes = boxes
  }

  /** Teleport to chair and play sit animation. WASD stands up. */
  sitAt(x: number, z: number, yaw: number): void {
    if (!this.entity) return
    this._sitting = true
    this.entity.setPosition(x, 0, z)
    this.entity.setEulerAngles(0, yaw, 0)
    this.entity.anim?.setInteger('speed', 0)
    this.entity.anim?.setInteger('sitting', 1)
  }

  /** End sit — resume normal movement. */
  standUp(): void {
    if (!this.entity) return
    this._sitting = false
    this.entity.anim?.setInteger('sitting', 0)
  }

  /** Teleport to bed position and play sleep animation. WASD wakes up. */
  sleepAt(x: number, z: number, yaw: number): void {
    if (!this.entity) return
    this._sleeping = true
    this.entity.setPosition(x, 0, z)
    this.entity.setEulerAngles(0, yaw, 0)
    this.entity.anim?.setInteger('speed', 0)
    this.entity.anim?.setInteger('sleeping', 1)
  }

  /** End sleep — resume normal movement. */
  wakeUp(): void {
    if (!this.entity) return
    this._sleeping = false
    this.entity.anim?.setInteger('sleeping', 0)
  }

  update(dt: number, camYaw = 0): void {
    if (!this.entity) return

    const dir = this._dir
    dir.set(0, 0, 0)
    if (this.input.isPressed(pc.KEY_W) || this.input.isPressed(pc.KEY_UP))    dir.z -= 1
    if (this.input.isPressed(pc.KEY_S) || this.input.isPressed(pc.KEY_DOWN))  dir.z += 1
    if (this.input.isPressed(pc.KEY_A) || this.input.isPressed(pc.KEY_LEFT))  dir.x -= 1
    if (this.input.isPressed(pc.KEY_D) || this.input.isPressed(pc.KEY_RIGHT)) dir.x += 1

    // Any movement key while sitting/sleeping → resume normal movement.
    if (this._sitting || this._sleeping) {
      if (dir.length() > 0) {
        if (this._sitting)  this.standUp()
        if (this._sleeping) this.wakeUp()
      } else {
        this.entity.anim!.setInteger('speed', 0)
        return
      }
    }

    const moving = dir.length() > 0
    if (moving) {
      dir.normalize()

      // Rotate camera-space input into world space using orbit yaw.
      // W always moves in the camera's forward direction regardless of orbit angle.
      const sinA = Math.sin(camYaw * pc.math.DEG_TO_RAD)
      const cosA = Math.cos(camYaw * pc.math.DEG_TO_RAD)
      const wx = dir.z * sinA + dir.x * cosA
      const wz = dir.z * cosA - dir.x * sinA
      dir.set(wx, 0, wz)

      const dx = dir.x * MOVE_SPEED * dt
      const dz = dir.z * MOVE_SPEED * dt
      const pos = this.entity.getPosition()
      const next = tryMove(pos, dx, dz, this.collisionBoxes, this._next)
      this.entity.setPosition(next.x, 0, next.z)

      // Face world movement direction (instant snap).
      // Model is +Z-native with CCW euler-Y rotation: facing(θ) = (sinθ, 0, cosθ).
      // Solving facing = (dir.x, 0, dir.z): sinθ = dir.x, cosθ = dir.z → θ = atan2(dir.x, dir.z).
      const targetYaw = Math.atan2(dir.x, dir.z) * pc.math.RAD_TO_DEG
      this.entity.setEulerAngles(0, targetYaw, 0)
    }

    this.entity.anim!.setInteger('speed', moving ? 1 : 0)
  }

  /** Teleport player to a new world position (e.g., after scene transition). */
  teleport(x: number, z: number, yaw = 180): void {
    if (!this.entity) return
    this.entity.setPosition(x, 0, z)
    this.entity.setEulerAngles(0, yaw, 0)
    // Force idle immediately — no walk animation bleed after teleport
    this.entity.anim?.setInteger('speed', 0)
  }

  getPosition(): pc.Vec3 {
    return this.entity?.getPosition() ?? pc.Vec3.ZERO.clone()
  }

  getEntity(): pc.Entity | null { return this.entity }

  destroy(): void {
    this.entity?.destroy()
    this.entity = null
  }
}
