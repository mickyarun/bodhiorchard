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

    if (isKayKitConfig(config)) {
      // KayKit character — reuse shared factory for GLB cache sharing
      const factory = kayKitFactory ?? new KayKitCharacterFactory(loader)
      const result = await factory.create(
        initial.userId, this.name, config,
        initial.x, 0, initial.z,
        initial.yaw, false,
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
    }

    this.targetX = initial.x
    this.targetZ = initial.z
    this.targetYaw = initial.yaw
  }

  /** Update target position from network data. */
  setTarget(player: PlayerData): void {
    this.targetX = player.x
    this.targetZ = player.z
    this.targetYaw = player.yaw
  }

  /** Per-frame interpolation toward target position. */
  update(): void {
    if (!this.entity) return
    const pos = this.entity.getPosition()
    const x = pos.x + (this.targetX - pos.x) * LERP_FACTOR
    const z = pos.z + (this.targetZ - pos.z) * LERP_FACTOR
    this.entity.setPosition(x, 0, z)

    const angles = this.entity.getEulerAngles()
    const yaw = angles.y + (this.targetYaw - angles.y) * LERP_FACTOR
    this.entity.setEulerAngles(0, yaw, 0)
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
