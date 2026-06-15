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
 * MinigameRoomClient — one Colyseus connection for one solo mini-game play.
 *
 * Each play creates a fresh private room (so sessions never collide). The
 * server is authoritative: it streams what to render via game-specific
 * messages, the client sends inputs through `send`, and the final outcome
 * arrives as `mg_result`. The component owns an instance and `destroy()`s it
 * on unmount.
 */
import { Client, getStateCallbacks, Room } from "@colyseus/sdk"
import { resolveColyseusUrl } from "./colyseusUrl"

/** Thin authoritative state synced from the room. */
export interface MinigameStateSnapshot {
  game: string
  phase: "playing" | "finished"
  score: number
  round: number
}

/** The recorded outcome, relayed from the bridge response on `mg_result`. */
export interface MinigameResult {
  recorded: boolean
  game: string
  score: number
  best_score: number
  is_new_best: boolean
  current_streak: number
  best_streak: number
  first_play_today: boolean
}

export interface MinigameAuth {
  userId: string
  name: string
  orgId: string
  token?: string
}

interface MinigameStateShape {
  game: string
  phase: string
  score: number
  round: number
}

export class MinigameRoomClient {
  private client: Client
  private room: Room | null = null

  /** Fires on every authoritative state delta (score, phase, round). */
  onState: ((snapshot: MinigameStateSnapshot) => void) | null = null
  /** Fires for each game-specific render message (e.g. firefly_sequence). */
  onEvent: ((type: string, payload: unknown) => void) | null = null
  /** Fires once when the server has recorded the final score. */
  onResult: ((result: MinigameResult) => void) | null = null

  constructor(serverUrl?: string) {
    this.client = new Client(serverUrl ?? resolveColyseusUrl())
  }

  /** Create + join a fresh room for one play of `game`. */
  async start(game: string, auth: MinigameAuth): Promise<void> {
    if (this.room) await this.leave()
    this.room = await this.client.create("minigame", {
      game,
      userId: auth.userId,
      name: auth.name,
      orgId: auth.orgId,
      token: auth.token ?? "",
    })
    this.room.onMessage("mg_result", (msg: unknown) => this.onResult?.(msg as MinigameResult))
    this.room.onMessage("*", (type: string | number, msg: unknown) => {
      const t = String(type)
      if (t === "mg_result") return // handled above
      this.onEvent?.(t, msg)
    })
    this.wireState()
  }

  /** Send a validated input to the server (the server scores it). */
  send(type: string, payload: unknown): void {
    this.room?.send("mg_input", { type, payload })
  }

  async leave(): Promise<void> {
    if (!this.room) return
    try {
      await this.room.leave()
    } catch {
      // Already disconnected — nothing to recover.
    }
    this.room = null
  }

  destroy(): void {
    void this.leave()
    this.onState = null
    this.onEvent = null
    this.onResult = null
  }

  private wireState(): void {
    if (!this.room) return
    const room = this.room as Room<MinigameStateShape>
    const $ = getStateCallbacks(room)
    const publish = (): void => {
      try {
        this.onState?.({
          game: room.state.game ?? "",
          phase: (room.state.phase as "playing" | "finished") ?? "playing",
          score: room.state.score ?? 0,
          round: room.state.round ?? 0,
        })
      } catch (err) {
        console.warn("[MinigameRoomClient] snapshot read skipped:", err)
      }
    }
    $(room.state).onChange(() => publish())
    publish()
  }
}
