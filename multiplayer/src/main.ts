/**
 * FlowDev Multiplayer Server — Colyseus WebSocket server.
 *
 * Rooms:
 *   "house" — House interior (one per house, max 10 players)
 *   "garden" — Shared garden world (stub for future)
 *
 * Default port: 2567 (Colyseus standard)
 */
import { defineServer, defineRoom } from "colyseus"
import { WebSocketTransport } from "@colyseus/ws-transport"
import { HouseRoom } from "./rooms/HouseRoom"
import { GardenRoom } from "./rooms/GardenRoom"

const port = parseInt(process.env.PORT || "2567", 10)

const server = defineServer({
  rooms: {
    house: defineRoom(HouseRoom),
    garden: defineRoom(GardenRoom),
  },

  transport: new WebSocketTransport({
    pingInterval: 10000,
    pingMaxRetries: 3,
  }),

  devMode: process.env.NODE_ENV !== "production",

  express: (app) => {
    app.get("/health", (_req, res) => {
      res.json({ status: "ok", rooms: ["house", "garden"] })
    })
  },
})

server.listen(port)
console.log(`[FlowDev Multiplayer] Listening on ws://localhost:${port}`)
