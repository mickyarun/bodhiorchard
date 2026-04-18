/**
 * NetworkedPlayer — remote player avatar for multiplayer.
 *
 * Spawns a Kenney character entity for each remote player,
 * interpolates position updates, and shows a name label.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../engine/assets/AssetLoader'
import { getCharacterGLB } from '../engine/assets/AssetManifest'
import type { Application } from '../engine/core/Application'
import type { PlayerData } from './ColyseusClient'
import { parseCharacterModel, isKayKitConfig } from '../engine/characters/CharacterConfig'
import { KayKitCharacterFactory } from '../engine/characters/KayKitCharacterFactory'
import { CharacterFactory } from '../engine/characters/CharacterFactory'

// Character model constants (matches PlayerController / CharacterFactory)
const CHAR_NATIVE_HEIGHT = 9.0
const CHAR_TARGET_HEIGHT = 1.0
const CHAR_SCALE = CHAR_TARGET_HEIGHT / CHAR_NATIVE_HEIGHT
const CHAR_Y_OFFSET = 1.0 * CHAR_SCALE

const LERP_FACTOR = 0.15  // position interpolation per frame

export class NetworkedPlayer {
  private entity: pc.Entity | null = null
  private label: pc.Entity | null = null
  private app: Application | null = null
  private targetX = 0
  private targetZ = 0
  private targetYaw = 0
  private seated = false

  readonly sessionId: string
  readonly name: string

  constructor(sessionId: string, name: string) {
    this.sessionId = sessionId
    this.name = name
  }

  /** Spawn the character entity under a parent (interiorRoot). */
  async spawn(
    parent: pc.Entity,
    loader: AssetLoader,
    app: Application,
    initial: PlayerData,
    kayKitFactory?: KayKitCharacterFactory,
  ): Promise<void> {
    const config = parseCharacterModel(initial.characterModel || null)
    const seated = initial.animState === 'sit' || initial.animState === 'sleep'

    if (isKayKitConfig(config)) {
      // KayKit character — reuse shared factory for GLB cache sharing
      const factory = kayKitFactory ?? new KayKitCharacterFactory(loader)
      const result = await factory.create(
        initial.userId, this.name, config,
        initial.x, 0, initial.z,
        initial.yaw, seated,
      )
      parent.addChild(result.entity)
      this.entity = result.entity
      this.app = app
    } else {
      // Legacy Kenney Blocky character
      const variant = config.characterId || CharacterFactory.getVariant(initial.userId, null)
      const glbPath = getCharacterGLB(variant)
      const asset = await loader.load(glbPath)
      const container = asset.resource as { instantiateRenderEntity(): pc.Entity }

      const wrapper = new pc.Entity(`Remote_${this.name}`)
      wrapper.setPosition(initial.x, 0, initial.z)
      wrapper.setEulerAngles(0, initial.yaw, 0)

      const renderEntity = container.instantiateRenderEntity()
      renderEntity.setLocalScale(CHAR_SCALE, CHAR_SCALE, CHAR_SCALE)
      renderEntity.setLocalPosition(0, CHAR_Y_OFFSET, 0)
      wrapper.addChild(renderEntity)

      // Name label
      this.addNameLabel(wrapper, app)

      parent.addChild(wrapper)
      this.entity = wrapper

      // Drive the anim component's sitting boolean if present
      wrapper.anim?.setBoolean('sitting', seated)
    }

    this.targetX = initial.x
    this.targetZ = initial.z
    this.targetYaw = initial.yaw
    this.seated = initial.animState === 'sit' || initial.animState === 'sleep'
  }

  /** Update target position and pose from network data. */
  setTarget(player: PlayerData): void {
    this.targetX = player.x
    this.targetZ = player.z
    this.targetYaw = player.yaw
    this.seated = player.animState === 'sit' || player.animState === 'sleep'
    // Apply pose transitions (sit/sleep/idle/walk) — server is authoritative.
    const anim = this.entity?.anim
    if (anim) {
      anim.setBoolean('sitting', this.seated)
    }
  }

  /** Per-frame interpolation toward target position. */
  update(): void {
    if (!this.entity) return

    // Seated NPCs snap to exact position+yaw (no drift from interpolation).
    // Walking NPCs interpolate smoothly with shortest-path yaw.
    if (this.seated) {
      this.entity.setPosition(this.targetX, 0, this.targetZ)
      this.entity.setEulerAngles(0, this.targetYaw, 0)
      return
    }

    const pos = this.entity.getPosition()
    const x = pos.x + (this.targetX - pos.x) * LERP_FACTOR
    const z = pos.z + (this.targetZ - pos.z) * LERP_FACTOR
    this.entity.setPosition(x, 0, z)

    // Shortest-path yaw interpolation: normalize delta to [-180, 180] so
    // the LERP takes the short arc (e.g., 350→10 goes +20, not −340).
    const current = this.entity.getEulerAngles().y
    let delta = this.targetYaw - current
    delta = delta - Math.round(delta / 360) * 360  // normalize to [-180, 180]
    this.entity.setEulerAngles(0, current + delta * LERP_FACTOR, 0)
  }

  despawn(): void {
    // Unregister billboard before destroying to prevent stale references
    if (this.label && this.app) {
      this.app.unregisterBillboard(this.label)
    }
    this.entity?.destroy()
    this.entity = null
    this.label = null
    this.app = null
  }

  private addNameLabel(wrapper: pc.Entity, app: Application): void {
    this.app = app
    this.label = new pc.Entity(`Label_${this.name}`)
    this.label.addComponent('element', {
      type: 'text',
      text: this.name,
      fontSize: 32,
      color: new pc.Color(1, 1, 1),
      anchor: new pc.Vec4(0.5, 0.5, 0.5, 0.5),
      pivot: new pc.Vec2(0.5, 0),
      width: 200,
      height: 40,
    })
    this.label.setLocalPosition(0, CHAR_TARGET_HEIGHT + 0.25, 0)
    // Billboard — face camera every frame
    app.registerBillboard(this.label)
    wrapper.addChild(this.label)
  }
}
