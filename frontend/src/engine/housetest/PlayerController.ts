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
import type { PhysicsWorld } from '../physics'

// ─── Character model constants (matches CharacterFactory) ────
const CHAR_NATIVE_HEIGHT = 9.0
const CHAR_TARGET_HEIGHT = 1.0
const CHAR_SCALE = CHAR_TARGET_HEIGHT / CHAR_NATIVE_HEIGHT
/** Lifts model feet (Y≈-1 native) to Y=0 in wrapper space. */
const CHAR_Y_OFFSET = 1.0 * CHAR_SCALE

// ─── Movement constants ──────────────────────────────────────
const MOVE_SPEED   = 3.0  // world units per second
const SPRINT_SPEED = 6.0  // 2× walk
const JUMP_HEIGHT  = 0.5  // peak Y
const JUMP_DURATION = 0.45 // seconds

// ─── Animation state graph ──────────────────────────────────
// Extended from LOCOMOTION_STATE_GRAPH (AnimUtils.ts) for house interiors.
// NOTE: uses INTEGER parameters (sitting=0/1) vs BOOLEAN in LOCOMOTION_STATE_GRAPH.
// KayKit characters use Sit for both chair sitting and bed sleeping (no lie-down clip).
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
    ],
  }],
  parameters: {
    speed:    { name: 'speed',    type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
    sitting:  { name: 'sitting',  type: pc.ANIM_PARAMETER_INTEGER, value: 0 },
  },
}

// ContainerWithAnims and findAnimTrack imported from shared AnimUtils

export class PlayerController {
  private loader: AssetLoader
  private input: InputManager
  private entity: pc.Entity | null = null
  private _isKayKit = false
  private collisionBoxes: CollisionBox[] = []
  private physics: PhysicsWorld | null = null
  private _sitting  = false
  private _sleeping = false
  private _jumpProgress = -1  // -1 = not jumping

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

      // Load extra animation GLBs and assign them as additional states
      const anim = result.entity.anim
      if (anim?.baseLayer) {
        const layer = anim.baseLayer
        const loadTracks = async (glb: string) => {
          const a = await this.loader.load(glb)
          return a.resource as ContainerWithAnims
        }
        const [general, simulation, tools] = await Promise.all([
          loadTracks('characters/kaykit/animations/general.glb'),
          loadTracks('characters/kaykit/animations/simulation.glb'),
          loadTracks('characters/kaykit/animations/tools.glb'),
        ])

        // Sleep — Death_A plays once and holds collapsed pose
        const death = findAnimTrack(general, 'Death_A')
        if (death) layer.assignAnimation('Sleep', death, 1, false)

        // Working — for laptop/desk interaction
        const working = findAnimTrack(tools, 'Working_A')
        if (working) layer.assignAnimation('Working', working)

        // Extra animations for the picker
        const extras: [string, ContainerWithAnims, string, boolean][] = [
          ['Cheering',    simulation, 'Cheering',        true],
          ['Waving',      simulation, 'Waving',          true],
          ['LieIdle',     simulation, 'Lie_Idle',        true],
          ['SitFloor',    simulation, 'Sit_Floor_Idle',  true],
          ['PushUps',     simulation, 'Push_Ups',        true],
          ['Interact',    general,    'Interact',        true],
          ['UseItem',     general,    'Use_Item',        true],
          ['Chopping',    tools,      'Chopping',        true],
          ['Hammering',   tools,      'Hammering',       true],
          ['Fishing',     tools,      'Fishing_Idle',    true],
        ]
        for (const [state, container, trackName, loop] of extras) {
          const track = findAnimTrack(container, trackName)
          if (track) layer.assignAnimation(state, track, 1, loop)
        }
      }

      root.addChild(result.entity)
      this.entity = result.entity
      this._isKayKit = true
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
      const sleep = findAnimTrack(container, 'death') ?? findAnimTrack(container, 'lie') ?? idle
      if (idle)  layer.assignAnimation('Idle',  idle)
      if (walk)  layer.assignAnimation('Walk',  walk)
      if (sit)   layer.assignAnimation('Sit',   sit)
      if (sleep) layer.assignAnimation('Sleep', sleep, 1, false)
    }

    root.addChild(wrapper)
    this.entity = wrapper
    return wrapper
  }

  /** Swap collision boxes when transitioning between scenes (manual AABB mode). */
  setCollisionBoxes(boxes: CollisionBox[]): void {
    this.collisionBoxes = boxes
    this.physics = null  // disable Rapier when using manual boxes
  }

  /** Use Rapier physics for collision (exterior mode). */
  setPhysics(physics: PhysicsWorld | null): void {
    this.physics = physics
  }

  /** Teleport to chair and play sit animation. WASD stands up. */
  sitAt(x: number, z: number, yaw: number, y = 0): void {
    if (!this.entity) return
    this._sitting = true
    this.entity.setPosition(x, y, z)
    this.entity.setEulerAngles(0, yaw, 0)
    const anim = this.entity.anim
    if (this._isKayKit) {
      anim?.setBoolean('sitting', true)
      anim?.setInteger('speed', 0)
    } else {
      anim?.setInteger('speed', 0)
      anim?.setInteger('sitting', 1)
    }
  }

  /** End sit — clear working state and force back to Idle. */
  standUp(): void {
    if (!this.entity) return
    this._sitting = false
    const anim = this.entity.anim
    if (!anim) return
    try { anim.setInteger('working', 0) } catch (e) { if (import.meta.env.DEV) console.debug('[PlayerCtrl] anim param missing:', e) }
    if (this._isKayKit) {
      anim.setBoolean('sitting', false)
    } else {
      anim.setInteger('sitting', 0)
    }
    try { anim.baseLayer?.transition('Idle', 0.2) } catch (e) { if (import.meta.env.DEV) console.debug('[PlayerCtrl] anim transition:', e) }
  }

  /** Teleport to bed and play Death_A animation for sleep. */
  sleepAt(x: number, z: number, yaw: number, y = 0): void {
    if (!this.entity) return
    this._sleeping = true
    this.entity.setPosition(x, y, z)
    this.entity.setEulerAngles(0, yaw, 0)
    const anim = this.entity.anim
    if (!anim) return
    anim.setInteger('speed', 0)
    if (this._isKayKit) {
      anim.setBoolean('sitting', false)
    } else {
      anim.setInteger('sitting', 0)
    }
    try { anim.baseLayer?.transition('Sleep', 0.3) } catch { /* state missing */ }
  }

  /** End sleep — reset to floor level and resume idle. */
  wakeUp(): void {
    if (!this.entity) return
    this._sleeping = false
    // Move character off the bed to floor level, slightly in front
    const pos = this.entity.getPosition()
    this.entity.setPosition(pos.x, 0, pos.z + 0.8)
    const anim = this.entity.anim
    if (!anim) return
    try { anim.baseLayer?.transition('Idle', 0.3) } catch (e) { if (import.meta.env.DEV) console.debug('[PlayerCtrl] anim transition:', e) }
  }

  /** Play a named animation state (for the animation picker UI). */
  playAnimation(stateName: string): void {
    const anim = this.entity?.anim
    if (!anim?.baseLayer) return
    try { anim.baseLayer.transition(stateName, 0.3) } catch (e) { if (import.meta.env.DEV) console.debug('[PlayerCtrl] anim state:', e) }
  }

  /** Get list of available animation state names. */
  getAnimationStates(): string[] {
    return ['Idle', 'Walk', 'Sit', 'Sleep', 'Working', 'Cheering', 'Waving',
            'LieIdle', 'SitFloor', 'PushUps', 'Interact', 'UseItem',
            'Chopping', 'Hammering', 'Fishing']
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

    const sprinting = this.input.isPressed(pc.KEY_SHIFT)
    const jumpPressed = this.input.wasPressed(pc.KEY_SPACE)

    // Jump trigger (only when not already jumping or sitting)
    if (jumpPressed && this._jumpProgress < 0 && !this._sitting && !this._sleeping) {
      this._jumpProgress = 0
    }

    // Jump arc (sine wave)
    if (this._jumpProgress >= 0) {
      this._jumpProgress += dt / JUMP_DURATION
      if (this._jumpProgress >= 1) {
        this._jumpProgress = -1
        const p = this.entity.getPosition()
        this.entity.setPosition(p.x, 0, p.z)
      } else {
        const jumpY = Math.sin(this._jumpProgress * Math.PI) * JUMP_HEIGHT
        const p = this.entity.getPosition()
        this.entity.setPosition(p.x, jumpY, p.z)
      }
    }

    const moving = dir.length() > 0
    if (moving) {
      dir.normalize()

      // Rotate camera-space input into world space using orbit yaw.
      const sinA = Math.sin(camYaw * pc.math.DEG_TO_RAD)
      const cosA = Math.cos(camYaw * pc.math.DEG_TO_RAD)
      const wx = dir.z * sinA + dir.x * cosA
      const wz = dir.z * cosA - dir.x * sinA
      dir.set(wx, 0, wz)

      const speed = sprinting ? SPRINT_SPEED : MOVE_SPEED
      const dx = dir.x * speed * dt
      const dz = dir.z * speed * dt

      if (this.physics) {
        // Rapier mode: character controller handles wall sliding
        this.physics.movePlayer(dx, dz)
        const p = this.physics.getPlayerPosition()
        const y = this._jumpProgress >= 0 ? this.entity.getPosition().y : 0
        this.entity.setPosition(p.x, y, p.z)
      } else {
        // Manual AABB mode (interior with furniture collision)
        const pos = this.entity.getPosition()
        const next = tryMove(pos, dx, dz, this.collisionBoxes, this._next)
        const y = this._jumpProgress >= 0 ? pos.y : 0
        this.entity.setPosition(next.x, y, next.z)
      }

      // Face world movement direction (instant snap).
      // Model is +Z-native with CCW euler-Y rotation: facing(θ) = (sinθ, 0, cosθ).
      // Solving facing = (dir.x, 0, dir.z): sinθ = dir.x, cosθ = dir.z → θ = atan2(dir.x, dir.z).
      const targetYaw = Math.atan2(dir.x, dir.z) * pc.math.RAD_TO_DEG
      this.entity.setEulerAngles(0, targetYaw, 0)
    }

    // Animation: 0=idle, 1=walk (sprint uses walk anim at faster movement)
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
