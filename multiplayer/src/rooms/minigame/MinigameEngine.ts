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

import type { MinigameRoomState } from "../../schema/MinigameRoomState"

/**
 * The slice of the room an engine is allowed to touch. Keeps engines decoupled
 * from Colyseus so they can be unit-tested with a fake host.
 */
export interface MinigameHost {
  readonly state: MinigameRoomState
  /** Send a render/feedback message to the solo player. */
  notify(type: string, message: unknown): void
  /** Signal game over — the room computes the final score and posts it. */
  finish(): void
}

/**
 * A server-authoritative mini-game. The engine owns the rules and the score;
 * the client only renders what `host.send` streams and submits inputs. One
 * generic `MinigameRoom` drives any engine, so adding a game is adding an
 * engine — not a room.
 */
export interface MinigameEngine {
  /** Begin play: seed state and stream the first render messages. */
  start(host: MinigameHost): void
  /** Handle one client input. Unknown types/payloads must be ignored, not trusted. */
  input(host: MinigameHost, type: string, payload: unknown): void
  /** Optional fixed-step update (wall-clock ms) for timed games. */
  tick?(host: MinigameHost, nowMs: number): void
  /** The authoritative final score. */
  finalScore(): number
}
