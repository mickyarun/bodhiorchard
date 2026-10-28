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
 * One-time tickets that let the server, and only the server, create a race.
 *
 * Colyseus lets any client call `create("race", options)`, and RaceRoom's
 * create options name the org, the host and the invitees. A race is meant to
 * be opened only by `OrgRaceHandler` for the verified host, so the handler
 * issues a ticket, passes it in the create options, and RaceRoom.onCreate
 * consumes it. A ticket never leaves the process, works once, and is revoked
 * if the create fails before the room consumed it.
 */
import { randomUUID } from "node:crypto"

const outstanding = new Set<string>()

/** A fresh ticket for one `matchMaker.createRoom("race", ...)` call. */
export function issueRaceCreateTicket(): string {
  const ticket = randomUUID()
  outstanding.add(ticket)
  return ticket
}

/** True, once, for a ticket this process issued; false for anything else. */
export function consumeRaceCreateTicket(ticket: unknown): boolean {
  return typeof ticket === "string" && outstanding.delete(ticket)
}

/** Drop a ticket that was not consumed (the create failed early). */
export function revokeRaceCreateTicket(ticket: string): void {
  outstanding.delete(ticket)
}
