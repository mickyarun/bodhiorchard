// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { ArraySchema, Schema, type } from "@colyseus/schema"

/** Compact org-room listing for a Backlash match that can be watched live. */
export class ActiveBacklashSummary extends Schema {
  @type("string") roomId = ""
  @type("string") hostUserId = ""
  @type("string") hostName = ""
  @type("string") invitedName = ""
  @type("string") phase = "lobby"
  @type("uint8") viewerCount = 0
  @type(["string"]) participantUserIds = new ArraySchema<string>()
}
