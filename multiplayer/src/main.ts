/**
 * Bodhiorchard Multiplayer Server — Colyseus WebSocket server.
 *
 * Rooms:
 *   "org"   — One per org, holds authoritative state for all members + agents.
 *             Drives character/agent simulation and fans out to all viewers.
 *   "house" — Per-house room for interior visitor-visitor visibility.
 *             (Owner visibility is handled via OrgRoom state since Phase 8.)
 *
 * HTTP endpoints:
 *   GET  /health             — Health check
 *   POST /internal/publish   — Backend → Colyseus event bridge (secret-protected)
 *
 * Default port: 2567 (Colyseus standard)
 */
import { defineServer, defineRoom } from "colyseus"
import { WebSocketTransport } from "@colyseus/ws-transport"
import { json as expressJson } from "express"
import type { Request, Response } from "express"
import { OrgRoom } from "./rooms/OrgRoom"
import { HouseRoom } from "./rooms/HouseRoom"
import { handleBridgePublish } from "./bridge/BridgeEndpoint"

const port = parseInt(process.env.PORT || "2567", 10)

const server = defineServer({
  rooms: {
    org: defineRoom(OrgRoom),
    house: defineRoom(HouseRoom),
  },

  transport: new WebSocketTransport({
    pingInterval: 10000,
    pingMaxRetries: 3,
  }),

  devMode: process.env.NODE_ENV !== "production",

  express: (app) => {
    // JSON body parser for /internal/* routes
    app.use("/internal", expressJson({ limit: "1mb" }))

    app.get("/health", (_req: Request, res: Response) => {
      res.json({ status: "ok", rooms: ["org", "house"] })
    })

    // Backend → Colyseus event bridge
    app.post("/internal/publish", handleBridgePublish)
  },
})

server.listen(port)
console.log(`[Bodhiorchard Multiplayer] Listening on ws://localhost:${port}`)
