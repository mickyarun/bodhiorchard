/**
 * CharacterSystem — Manages all character entities in the scene.
 *
 * Creates one character per member, places them based on presence:
 *   - 'active' or undefined → seated at a building (desk, coffee bar, etc.)
 *   - 'on_break' → at pool or coffee bar seats
 *   - 'at_home' → at their house bed position
 *
 * Phase 3 scope: static placement with idle/sit animations.
 * WASD player control will be added in a later iteration.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { AssetLoader } from '../assets/AssetLoader'
import type { EngineMember } from '../types'
import type { InteractionPoint } from './InteractionPoint'
import { CharacterFactory, type CharacterEntity } from './CharacterFactory'
import type { HouseResult } from '../buildings/HouseBuilder'
import { disposeMaterial } from '../utils/EntityUtils'

export class CharacterSystem {
  private factory: CharacterFactory
  private characters: CharacterEntity[] = []
  private app: Application | null = null

  constructor(loader: AssetLoader) {
    this.factory = new CharacterFactory(loader)
  }

  /**
   * Build characters for all members and add them to the scene.
   *
   * @param app - PlayCanvas application wrapper
   * @param members - Team members to create characters for
   * @param memberHouseMap - Maps member user_id → house data (bed position, seats)
   * @param allSeats - All registered seats from all buildings
   */
  async build(
    app: Application,
    members: EngineMember[],
    memberHouseMap: Map<string, HouseResult>,
    allSeats: InteractionPoint[],
  ): Promise<void> {
    this.app = app

    // Track which seats are taken so we don't double-assign
    const takenSeats = new Set<string>()

    for (const member of members) {
      const variant = CharacterFactory.getVariant(
        member.user_id,
        member.character_model,
      )
      const house = memberHouseMap.get(member.user_id)
      const placement = this.getPlacement(member, house, allSeats, takenSeats)

      const character = await this.factory.create(
        member.user_id,
        member.name,
        variant,
        placement.x,
        placement.y,
        placement.z,
        placement.yaw,
        placement.sitting,
      )

      // Add to scene — animation starts on first tick (activate=true set in factory)
      app.root.addChild(character.entity)
      this.characters.push(character)

      // Register name label for billboard facing
      const label = character.entity.findByTag('billboard')[0] as pc.Entity | undefined
      if (label) app.registerBillboard(label)
    }
  }

  /** Determine where to place a character based on presence. */
  private getPlacement(
    member: EngineMember,
    house: HouseResult | undefined,
    allSeats: InteractionPoint[],
    takenSeats: Set<string>,
  ): { x: number; y: number; z: number; yaw: number; sitting: boolean } {
    const presence = member.presence ?? 'active'

    // 'at_home' → stand at house bed position
    if (presence === 'at_home' && house) {
      return {
        x: house.bedPosition.x,
        y: 0,
        z: house.bedPosition.z,
        yaw: 0,
        sitting: false,
      }
    }

    // 'active' → try to seat at their house desk first
    if (presence === 'active' && house) {
      const deskSeat = house.seats.find(s => !takenSeats.has(s.id))
      if (deskSeat) {
        takenSeats.add(deskSeat.id)
        return {
          x: deskSeat.x,
          y: deskSeat.y,
          z: deskSeat.z,
          yaw: deskSeat.yaw,
          sitting: true,
        }
      }
    }

    // 'on_break' → try pool or coffee bar seats
    if (presence === 'on_break') {
      const breakZones = ['pool_resort', 'coffee_bar']
      for (const zone of breakZones) {
        const seat = allSeats.find(s => s.zone === zone && !takenSeats.has(s.id))
        if (seat) {
          takenSeats.add(seat.id)
          return {
            x: seat.x,
            y: seat.y,
            z: seat.z,
            yaw: seat.yaw,
            sitting: true,
          }
        }
      }
    }

    // Fallback: any available seat
    const anySeat = allSeats.find(s => !takenSeats.has(s.id))
    if (anySeat) {
      takenSeats.add(anySeat.id)
      return {
        x: anySeat.x,
        y: anySeat.y,
        z: anySeat.z,
        yaw: anySeat.yaw,
        sitting: true,
      }
    }

    // Last resort: stand at house or origin
    if (house) {
      return {
        x: house.bedPosition.x,
        y: 0,
        z: house.bedPosition.z,
        yaw: 0,
        sitting: false,
      }
    }

    return { x: 0, y: 0, z: 0, yaw: 0, sitting: false }
  }

  /** Get all character entities (for Phase 5 interaction picking). */
  getCharacters(): CharacterEntity[] {
    return this.characters
  }

  /** Find a character by member ID. */
  getCharacter(memberId: string): CharacterEntity | undefined {
    return this.characters.find(c => c.memberId === memberId)
  }

  destroy(): void {
    for (const char of this.characters) {
      if (this.app) {
        const label = char.entity.findByTag('billboard')[0] as pc.Entity | undefined
        if (label) this.app.unregisterBillboard(label)
      }
      // Dispose label material + texture before destroying entity (GPU resource cleanup)
      const labelEntity = char.entity.findByName('NameLabel') as pc.Entity | null
      if (labelEntity?.render?.meshInstances[0]) {
        disposeMaterial(labelEntity.render.meshInstances[0].material)
      }
      char.entity.destroy()
    }
    this.characters = []
    this.app = null
    this.factory.clear()
  }
}
