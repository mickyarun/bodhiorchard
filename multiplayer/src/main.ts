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
 * Glideship Multiplayer Server — Colyseus WebSocket server.
 *
 * Rooms:
 *   "org"       — One per org, holds authoritative state for all members + agents.
 *                 Drives character/agent simulation and fans out to all viewers.
 *   "house"     — Per-house room for interior visitor-visitor visibility.
 *                 (Owner visibility is handled via OrgRoom state since Phase 8.)
 *   "coffeebar" — One per org. Shared queue + brewing state for the coffee bar
 *                 interior. Every visitor across the org joins the same room.
 *   "cafeteria" — One per org. Shared queue + cooking state for the cafeteria
 *                 interior. Mirrors the coffee bar room with meal orders.
 *
 * HTTP endpoints:
 *   GET  /health             — Health check
 *   POST /internal/publish   — Backend → Colyseus event bridge (secret-protected)
 *
 * Default port: 2567 (Colyseus standard)
 */
import { defineServer } from "colyseus"
import { WebSocketTransport } from "@colyseus/ws-transport"
import { json as expressJson } from "express"
import type { Request, Response } from "express"
import { roomDefinitions } from "./roomDefinitions"
import { handleBridgePublish } from "./bridge/BridgeEndpoint"

const port = parseInt(process.env.PORT || "2567", 10)

const server = defineServer({
  rooms: roomDefinitions,

  transport: new WebSocketTransport({
    pingInterval: 10000,
    pingMaxRetries: 3,
  }),

  // Colyseus dev mode restores rooms across restarts from cached state. It is
  // off unless explicitly asked for, never inferred from a missing NODE_ENV.
  devMode: process.env.MULTIPLAYER_DEV_MODE === "1",

  express: (app) => {
    // JSON body parser for /internal/* routes
    app.use("/internal", expressJson({ limit: "1mb" }))

    app.get("/health", (_req: Request, res: Response) => {
      res.json({
        status: "ok",
        rooms: ["org", "house", "coffeebar", "cafeteria", "race", "minigame", "backlash"],
      })
    })

    // Backend → Colyseus event bridge
    app.post("/internal/publish", handleBridgePublish)
  },
})

server.listen(port)
console.log(`[Glideship Multiplayer] Listening on ws://localhost:${port}`)
