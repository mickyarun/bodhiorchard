/**
 * FurnitureState — per-item furniture placement (future customization).
 *
 * When house customization is added, each placed furniture item
 * will be an entry in the room's furniture MapSchema.
 * For now this schema defines the contract for future use.
 */
import { Schema, type } from "@colyseus/schema"

export class FurnitureState extends Schema {
  @type("string") id: string = ""
  @type("string") assetKey: string = ""
  @type("number") x: number = 0
  @type("number") y: number = 0
  @type("number") z: number = 0
  @type("number") rotation: number = 0
  @type("string") ownerId: string = ""  // user who placed this item
}
