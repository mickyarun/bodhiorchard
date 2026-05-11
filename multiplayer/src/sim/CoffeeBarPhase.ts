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
 * CoffeeBarPhase — pure phase-transition logic for the coffee machine.
 *
 * Extracted from CoffeeBarRoom so the state machine can be unit-tested
 * without a live Colyseus server. The room calls advancePhase() every
 * simulation tick and applies the returned mutations.
 *
 * Phases: idle → approaching → brewing → dispensed → idle
 *   - idle: if queue non-empty, dequeue first entry and enter approaching.
 *   - approaching: character walks to machine for COFFEE_PHASE_MS.approaching.
 *   - brewing: drink brews for COFFEE_PHASE_MS.brewing.
 *   - dispensed: waits for client ack or COFFEE_PHASE_MS.dispensed timeout.
 */
import { COFFEE_PHASE_MS } from "./CoffeeMenu"
import type { CoffeeActionPhase } from "../schema/CoffeeBarState"

export interface PhaseSnapshot {
  phase: CoffeeActionPhase
  phaseStartMs: number
  userId: string
  drink: string
}

export interface QueueEntry {
  userId: string
  drink: string
}

export interface PhaseTickResult {
  /** New snapshot to apply. Null means no change. */
  next: PhaseSnapshot | null
  /** Number of queue entries consumed (0 or 1). */
  dequeued: number
  /** True when a drink was just dispensed (for "Refreshed" events). */
  justDispensed: boolean
  /** True when a cycle just completed (for NPC return-to-seat events). */
  justCompleted: boolean
}

const NO_CHANGE: PhaseTickResult = {
  next: null,
  dequeued: 0,
  justDispensed: false,
  justCompleted: false,
}

/**
 * Compute the next phase snapshot given the current one and the front of the
 * queue. Does not mutate inputs. Callers apply `next` and pop `dequeued`
 * entries from the queue.
 */
export function advancePhase(
  current: PhaseSnapshot,
  queueHead: QueueEntry | null,
  now: number,
): PhaseTickResult {
  const elapsed = now - current.phaseStartMs

  switch (current.phase) {
    case "idle": {
      if (!queueHead) return NO_CHANGE
      return {
        next: {
          phase: "approaching",
          phaseStartMs: now,
          userId: queueHead.userId,
          drink: queueHead.drink,
        },
        dequeued: 1,
        justDispensed: false,
        justCompleted: false,
      }
    }
    case "approaching": {
      if (elapsed < COFFEE_PHASE_MS.approaching) return NO_CHANGE
      return {
        next: { ...current, phase: "brewing", phaseStartMs: now },
        dequeued: 0,
        justDispensed: false,
        justCompleted: false,
      }
    }
    case "brewing": {
      if (elapsed < COFFEE_PHASE_MS.brewing) return NO_CHANGE
      return {
        next: { ...current, phase: "dispensed", phaseStartMs: now },
        dequeued: 0,
        justDispensed: true,
        justCompleted: false,
      }
    }
    case "dispensed": {
      if (elapsed < COFFEE_PHASE_MS.dispensed) return NO_CHANGE
      // Timeout without ack — return to idle so the queue can advance.
      return {
        next: {
          phase: "idle",
          phaseStartMs: now,
          userId: "",
          drink: "",
        },
        dequeued: 0,
        justDispensed: false,
        justCompleted: true,
      }
    }
  }
}

/**
 * Handle a client's "coffee_ack_dispense" — advance from dispensed to idle
 * immediately. If not in dispensed phase or the userId doesn't match, no-op.
 */
export function acknowledgeDispense(
  current: PhaseSnapshot,
  userId: string,
  now: number,
): PhaseTickResult {
  if (current.phase !== "dispensed") return NO_CHANGE
  if (current.userId !== userId) return NO_CHANGE
  return {
    next: {
      phase: "idle",
      phaseStartMs: now,
      userId: "",
      drink: "",
    },
    dequeued: 0,
    justDispensed: false,
    justCompleted: true,
  }
}
