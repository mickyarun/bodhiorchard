/**
 * VehicleController — Local player mount/dismount and vehicle movement.
 *
 * When active, this controller takes over from the TakeoverController's
 * normal walking mode. The character entity is parented to the vehicle
 * at the mount offset, and the physics capsule is resized for the vehicle.
 *
 * Movement reuses TakeoverController's camera-relative WASD logic but
 * applies the vehicle's speed multiplier. The horse's animation speed
 * is tied to movement speed (idle → walk → gallop).
 */
import * as pc from 'playcanvas'
import type { InputManager } from '../input/InputManager'
import type { PhysicsWorld } from '../physics'
import { VehicleFactory, type VehicleEntity } from './VehicleFactory'
import type { VehicleDef } from './VehicleManifest'
import type { AssetLoader } from '../assets/AssetLoader'

// Base movement speed (same as TakeoverController)
const WALK_SPEED = 3.0

export class VehicleController {
  private factory: VehicleFactory
  private vehicle: VehicleEntity | null = null
  private characterEntity: pc.Entity | null = null
  private physics: PhysicsWorld | null = null
  private input: InputManager
  private _active = false
  private _mounting = false

  // Scratch vector
  private readonly _dir = new pc.Vec3()

  constructor(input: InputManager, loader: AssetLoader) {
    this.input = input
    this.factory = new VehicleFactory(loader)
  }

  get isActive(): boolean { return this._active }

  /** Current vehicle world position (for camera follow + broadcast). */
  getPosition(): pc.Vec3 | null {
    return this.vehicle?.entity.getPosition() ?? null
  }

  /** Current vehicle yaw in degrees (for multiplayer broadcast). */
  getYaw(): number {
    return this.vehicle?.entity.getEulerAngles().y ?? 0
  }

  /**
   * Mount a vehicle at the character's current position.
   * - Spawns the vehicle entity
   * - Parents the character to the vehicle's mount offset
   * - Recreates the physics capsule with vehicle dimensions
   * - Switches character anim to riding pose
   */
  async mount(
    def: VehicleDef,
    characterEntity: pc.Entity,
    physics: PhysicsWorld,
    parentRoot: pc.Entity,
  ): Promise<void> {
    if (this._active || this._mounting) return
    this._mounting = true

    this.characterEntity = characterEntity
    this.physics = physics

    const pos = characterEntity.getPosition()
    const yaw = characterEntity.getEulerAngles().y

    // Create vehicle at character position
    this.vehicle = await this.factory.create(def, pos.x, pos.z, yaw)
    parentRoot.addChild(this.vehicle.entity)

    // Parent character to the vehicle's mount offset.
    // Counter-scale so the character stays at world-scale 1.0
    // despite the vehicle being scaled to def.scale.
    const inv = 1 / def.scale
    characterEntity.reparent(this.vehicle.entity)
    characterEntity.setLocalPosition(
      def.mountOffset.x * inv,
      def.mountOffset.y * inv,
      def.mountOffset.z * inv,
    )
    characterEntity.setLocalScale(inv, inv, inv)
    characterEntity.setLocalEulerAngles(0, 0, 0)

    // Freeze character in idle pose while mounted
    const anim = characterEntity.anim
    if (anim) {
      anim.setInteger('speed', 0)
      anim.setBoolean('sitting', false)
    }

    // Resize physics capsule for the vehicle
    physics.destroyPlayer()
    physics.createPlayer(pos.x, pos.z, def.physicsRadius, def.physicsHalfHeight)

    this._active = true
    this._mounting = false
  }

  /**
   * Dismount the vehicle.
   * - Unparents the character from the vehicle
   * - Destroys the vehicle entity
   * - Restores the character physics capsule
   * Returns the dismount position for the character.
   */
  dismount(): { x: number; z: number } | null {
    if (!this._active || !this.vehicle || !this.characterEntity || !this.physics) return null

    // Get current world position before unparenting
    const vehiclePos = this.vehicle.entity.getPosition()
    const dismountX = vehiclePos.x
    const dismountZ = vehiclePos.z

    // Unparent character from vehicle
    const scene = this.vehicle.entity.parent
    if (scene) {
      this.characterEntity.reparent(scene)
    }
    this.characterEntity.setPosition(dismountX, 0, dismountZ)
    this.characterEntity.setLocalScale(1, 1, 1)

    // Restore character animation state
    const anim = this.characterEntity.anim
    if (anim) {
      anim.setBoolean('sitting', false)
      anim.setInteger('speed', 0)
    }

    // Destroy vehicle entity
    this.factory.destroy(this.vehicle)
    this.vehicle = null

    // Restore character-sized physics capsule
    this.physics.destroyPlayer()
    this.physics.createPlayer(dismountX, dismountZ)

    this._active = false
    this._mounting = false
    this.characterEntity = null
    this.physics = null

    return { x: dismountX, z: dismountZ }
  }

  /**
   * Per-frame update when mounted.
   * Handles WASD movement with vehicle speed multiplier and
   * horse animation transitions based on movement speed.
   */
  update(dt: number, camYaw: number): void {
    if (!this._active || !this.vehicle || !this.physics) return

    const dir = this._dir
    dir.set(0, 0, 0)
    if (this.input.isPressed(pc.KEY_W) || this.input.isPressed(pc.KEY_UP))    dir.z -= 1
    if (this.input.isPressed(pc.KEY_S) || this.input.isPressed(pc.KEY_DOWN))  dir.z += 1
    if (this.input.isPressed(pc.KEY_A) || this.input.isPressed(pc.KEY_LEFT))  dir.x -= 1
    if (this.input.isPressed(pc.KEY_D) || this.input.isPressed(pc.KEY_RIGHT)) dir.x += 1

    const sprinting = this.input.isPressed(pc.KEY_SHIFT)
    const moving = dir.length() > 0
    const def = this.vehicle.def

    if (moving) {
      dir.normalize()

      // Camera-relative direction (same logic as TakeoverController)
      const sinA = Math.sin(camYaw * pc.math.DEG_TO_RAD)
      const cosA = Math.cos(camYaw * pc.math.DEG_TO_RAD)
      const wx = dir.z * sinA + dir.x * cosA
      const wz = dir.z * cosA - dir.x * sinA

      const baseSpeed = sprinting ? WALK_SPEED * 2 : WALK_SPEED
      const speed = baseSpeed * def.speedMultiplier
      this.physics.movePlayer(wx * speed * dt, wz * speed * dt)

      // Face movement direction (rotate entire vehicle)
      const yaw = Math.atan2(wx, wz) * pc.math.RAD_TO_DEG
      this.vehicle.entity.setEulerAngles(0, yaw, 0)
    }

    // Step physics + sync vehicle position
    this.physics.step()
    const p = this.physics.getPlayerPosition()
    this.vehicle.entity.setPosition(p.x, 0, p.z)

    // Horse animation: idle → walk → gallop based on movement
    this.updateVehicleAnimation(moving, sprinting)
  }

  private updateVehicleAnimation(moving: boolean, sprinting: boolean): void {
    if (!this.vehicle) return

    const anim = this.vehicle.entity.anim
    if (!anim) return

    // Drive the state graph via the "speed" parameter:
    //   0 = Idle, 1 = Walk, 2 = Gallop
    const speed = !moving ? 0 : sprinting ? 2 : 1
    anim.setInteger('speed', speed)
  }
}
