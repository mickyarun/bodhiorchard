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
 * PlayerController — keyboard-driven KayKit character with AABB collision.
 *
 * Loads a KayKit character via the shared factory, drives its locomotion
 * state graph (idle / walk / sit / sleep) via the AnimComponent, and
 * moves with WASD under AABB slide collision.
 *
 * Note: Using setPosition() directly (no rigidbody). When integrating into
 * the main dashboard, swap to Dynamic RigidBody + applyForce() with Ammo.js
 * for proper physics collision.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { InputManager } from '../input/InputManager'
import { parseCharacterModel } from '../characters/CharacterConfig'
import { KayKitCharacterFactory } from '../characters/KayKitCharacterFactory'
import { type ContainerWithAnims, findAnimTrack } from '../characters/AnimUtils'
import { tryMove, type CollisionBox } from './CollisionSystem'
import type { PhysicsWorld } from '../physics'

// ─── Movement constants ──────────────────────────────────────
const MOVE_SPEED   = 3.0  // world units per second
const SPRINT_SPEED = 6.0  // 2× walk
const JUMP_HEIGHT  = 0.5  // peak Y
const JUMP_DURATION = 0.45 // seconds

export class PlayerController {
  private loader: AssetLoader
  private input: InputManager
  private entity: pc.Entity | null = null
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

    // KayKit character — shared factory builds entity with animations + colors
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

      // Extra animations for the picker. Speed column lets us slow tracks
      // that otherwise read as twitchy (Use_Item is the drink reaction —
      // KayKit plays it at "barista snap" tempo by default).
      const extras: [string, ContainerWithAnims, string, boolean, number][] = [
        ['Cheering',    simulation, 'Cheering',        true,  1.0],
        ['Waving',      simulation, 'Waving',          true,  1.0],
        ['LieIdle',     simulation, 'Lie_Idle',        true,  1.0],
        ['SitFloor',    simulation, 'Sit_Floor_Idle',  true,  1.0],
        ['PushUps',     simulation, 'Push_Ups',        true,  1.0],
        ['Interact',    general,    'Interact',        true,  1.0],
        ['UseItem',     general,    'Use_Item',        true,  0.4],
        ['Chopping',    tools,      'Chopping',        true,  1.0],
        ['Hammering',   tools,      'Hammering',       true,  1.0],
        ['Fishing',     tools,      'Fishing_Idle',    true,  1.0],
      ]
      for (const [state, container, trackName, loop, speed] of extras) {
        const track = findAnimTrack(container, trackName)
        if (track) layer.assignAnimation(state, track, speed, loop)
      }
    }

    root.addChild(result.entity)
    this.entity = result.entity
    return result.entity
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
    anim?.setBoolean('sitting', true)
    anim?.setInteger('speed', 0)
  }

  /** End sit — nudge away from furniture to avoid collision trapping. */
  standUp(): void {
    if (!this.entity) return
    this._sitting = false

    // Nudge player backward (away from furniture) to escape collision
    const pos = this.entity.getPosition()
    const yaw = this.entity.getEulerAngles().y * (Math.PI / 180)
    this.entity.setPosition(
      pos.x + Math.sin(yaw) * 0.5,
      0,
      pos.z + Math.cos(yaw) * 0.5,
    )

    const anim = this.entity.anim
    if (!anim) return
    try { anim.setInteger('working', 0) } catch (e) { if (import.meta.env.DEV) console.debug('[PlayerCtrl] anim param missing:', e) }
    anim.setBoolean('sitting', false)
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
    anim.setBoolean('sitting', false)
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
        return  // skip movement on the stand-up frame
      } else {
        this.entity.anim?.setInteger('speed', 0)
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
