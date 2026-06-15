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
 * MinigameRoom — authoritative Colyseus room for ONE solo mini-game play.
 *
 * The whole point: the server runs the game and computes the score, so the
 * client can't self-report. One room per play (`maxClients = 1`); a per-game
 * engine (`FireflyEngine` / `FishingEngine` / `PollenEngine`) owns the rules.
 * Lifecycle:
 *   onCreate: pick the engine from `options.game`, thin state, message handler.
 *   onAuth:   verify the JWT (trust boundary) → authoritative userId/orgId.
 *   onJoin:   start the engine + (for timed games) the 20Hz sim loop.
 *   finish:   POST the server-computed score via the bridge, relay the outcome.
 */
import { Room, Client } from "colyseus"
import { MinigameRoomState } from "../schema/MinigameRoomState"
import type { MinigameEngine, MinigameHost } from "./minigame/MinigameEngine"
import { FireflyEngine } from "./minigame/FireflyEngine"
import { FishingEngine } from "./minigame/FishingEngine"
import { PollenEngine } from "./minigame/PollenEngine"
import { postMinigameResults, verifyUserToken } from "../bridge/BackendClient"

const SIM_TICK_MS = 50
/** Reap an abandoned room (player left a game open) after this long. */
const MAX_GAME_MS = 5 * 60 * 1000
const GAMES = new Set(["firefly", "fishing", "pollen_pop"])

interface JoinOptions {
  game?: string
  userId?: string
  name?: string
  orgId?: string
  token?: string
}

export class MinigameRoom extends Room<{ state: MinigameRoomState }> implements MinigameHost {
  maxClients = 1

  private engine: MinigameEngine | null = null
  private simHandle: NodeJS.Timeout | null = null
  private posted = false
  private userName = ""

  onCreate(rawOptions: unknown): void {
    const opts = (rawOptions ?? {}) as JoinOptions
    const state = new MinigameRoomState()
    state.game = typeof opts.game === "string" && GAMES.has(opts.game) ? opts.game : ""
    state.phase = "playing"
    this.setState(state)
    this.autoDispose = true
    this.onMessage("mg_input", (client, data: unknown) => this.handleInput(client, data))
    // Safety net: an abandoned room (game left open, never finished) is reaped.
    this.clock.setTimeout(() => this.endGame(), MAX_GAME_MS)
  }

  async onAuth(_client: Client, options: JoinOptions): Promise<JoinOptions> {
    const claimedOrg = options.orgId ?? ""
    if (!options.token) {
      if (process.env.NODE_ENV === "production") throw new Error("auth token required")
      console.warn(`[MinigameRoom] dev-mode join without token userId=${options.userId}`)
      return options
    }
    const result = await verifyUserToken(options.token, claimedOrg)
    if (!result.valid) {
      const reason = result.reason ?? "token_invalid"
      if (reason === "backend_unreachable") throw new Error("auth backend unreachable")
      if (reason === "backend_http_error") throw new Error("auth backend rejected request")
      throw new Error("invalid auth token — JWT may be expired, try refreshing the page")
    }
    // If the client claimed an org, it must match the token's — defence in depth
    // (the returned orgId is the token's regardless, but reject a mismatched claim).
    if (claimedOrg && result.org_id && result.org_id !== claimedOrg) {
      throw new Error("token org mismatch")
    }
    // Authoritative identity from the verified token replaces client claims.
    return {
      ...options,
      userId: result.user_id ?? options.userId,
      name: result.name ?? options.name,
      orgId: result.org_id ?? claimedOrg,
    }
  }

  onJoin(client: Client, options: JoinOptions): void {
    if (!this.state.game) {
      client.send("mg_error", { reason: "unknown_game" })
      this.disconnect()
      return
    }
    this.state.userId = options.userId ?? ""
    this.state.orgId = options.orgId ?? ""
    this.userName = options.name ?? ""
    client.userData = { userId: this.state.userId }

    const engine = makeEngine(this.state.game)
    if (!engine) {
      this.disconnect()
      return
    }
    this.engine = engine
    engine.start(this)
    if (engine.tick) {
      this.simHandle = setInterval(() => {
        if (this.state.phase === "playing") engine.tick?.(this, Date.now())
      }, SIM_TICK_MS)
    }
  }

  onDispose(): void {
    this.stopSim()
  }

  // ─── MinigameHost ────────────────────────
  notify(type: string, message: unknown): void {
    this.broadcast(type, message)
  }

  scheduleAfter(ms: number, fn: () => void): void {
    // Room clock auto-clears on dispose; guard so a queued round-advance can't
    // run after the game has already finished.
    this.clock.setTimeout(() => {
      if (this.state.phase === "playing") fn()
    }, ms)
  }

  finish(): void {
    this.endGame()
  }

  // ─── internals ───────────────────────────
  private handleInput(_client: Client, data: unknown): void {
    if (this.state.phase !== "playing" || !this.engine) return
    if (typeof data !== "object" || data === null) return
    const { type, payload } = data as { type?: unknown; payload?: unknown }
    if (typeof type !== "string") return
    this.engine.input(this, type, payload)
  }

  private endGame(): void {
    if (this.state.phase === "finished") return
    this.stopSim()
    this.state.phase = "finished"
    const score = this.engine ? this.engine.finalScore() : 0
    this.state.score = score
    void this.postAndRelay(score)
  }

  private async postAndRelay(score: number): Promise<void> {
    if (this.posted) return
    this.posted = true
    if (!this.state.userId || !this.state.game) {
      this.broadcast("mg_result", { recorded: false, game: this.state.game, score })
      return
    }
    const result = await postMinigameResults({
      sessionId: this.roomId,
      orgId: this.state.orgId,
      userId: this.state.userId,
      userName: this.userName,
      game: this.state.game,
      score,
    }).catch((err: unknown) => {
      console.error(`[MinigameRoom ${this.roomId}] postMinigameResults failed:`, err)
      return null
    })
    this.broadcast("mg_result", result ?? { recorded: false, game: this.state.game, score })
  }

  private stopSim(): void {
    if (this.simHandle) {
      clearInterval(this.simHandle)
      this.simHandle = null
    }
  }
}

function makeEngine(game: string): MinigameEngine | null {
  switch (game) {
    case "firefly":
      return new FireflyEngine()
    case "fishing":
      return new FishingEngine()
    case "pollen_pop":
      return new PollenEngine()
    default:
      return null
  }
}

export { MinigameRoomState }
