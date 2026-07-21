// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { ArraySchema, MapSchema, Schema, type } from "@colyseus/schema"

export class BacklashPlayerState extends Schema {
  @type("string") userId = ""
  @type("string") name = ""
  @type("string") color = ""
  @type("boolean") connected = false
  @type("boolean") rematchReady = false
  @type("uint8") capturedOverlings = 0
}

export class BacklashRoomState extends Schema {
  @type("string") orgId = ""
  @type("string") hostUserId = ""
  @type("string") invitedUserId = ""
  @type("string") phase = "lobby"
  @type("string") turnColor = "white"
  @type("string") turnUserId = ""
  @type("string") matchId = ""
  @type("string") winnerId = ""
  @type("string") outcome = ""
  @type("string") outcomeReason = ""
  @type("int16") lockedJumpIndex = -1
  @type("int16") pendingPromotionIndex = -1
  @type("uint16") revision = 0
  @type("uint16") moveCount = 0
  @type("float64") turnDeadlineMs = 0
  @type(["string"]) board = new ArraySchema<string>()
  @type(["uint8"]) legalTargets = new ArraySchema<number>()
  @type({ map: BacklashPlayerState }) players = new MapSchema<BacklashPlayerState>()
}
