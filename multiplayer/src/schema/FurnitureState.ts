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
