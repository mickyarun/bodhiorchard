// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * CafeteriaPhase — pure phase-transition logic for the cafeteria counter.
 *
 * Mirrors CoffeeBarPhase exactly with renamed fields. Extracted from
 * CafeteriaRoom so the state machine is unit-testable without a live
 * Colyseus server.
 *
 * Phases: idle → approaching → cooking → dispensed → idle
 */
import { CAFETERIA_PHASE_MS } from "./CafeteriaMenu"
import type { CafeteriaActionPhase } from "../schema/CafeteriaState"

export interface PhaseSnapshot {
  phase: CafeteriaActionPhase
  phaseStartMs: number
  userId: string
  meal: string
}

export interface QueueEntry {
  userId: string
  meal: string
}

export interface PhaseTickResult {
  next: PhaseSnapshot | null
  dequeued: number
  justDispensed: boolean
  justCompleted: boolean
}

const NO_CHANGE: PhaseTickResult = {
  next: null,
  dequeued: 0,
  justDispensed: false,
  justCompleted: false,
}

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
          meal: queueHead.meal,
        },
        dequeued: 1,
        justDispensed: false,
        justCompleted: false,
      }
    }
    case "approaching": {
      if (elapsed < CAFETERIA_PHASE_MS.approaching) return NO_CHANGE
      return {
        next: { ...current, phase: "cooking", phaseStartMs: now },
        dequeued: 0,
        justDispensed: false,
        justCompleted: false,
      }
    }
    case "cooking": {
      if (elapsed < CAFETERIA_PHASE_MS.cooking) return NO_CHANGE
      return {
        next: { ...current, phase: "dispensed", phaseStartMs: now },
        dequeued: 0,
        justDispensed: true,
        justCompleted: false,
      }
    }
    case "dispensed": {
      if (elapsed < CAFETERIA_PHASE_MS.dispensed) return NO_CHANGE
      return {
        next: {
          phase: "idle",
          phaseStartMs: now,
          userId: "",
          meal: "",
        },
        dequeued: 0,
        justDispensed: false,
        justCompleted: true,
      }
    }
  }
}

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
      meal: "",
    },
    dequeued: 0,
    justDispensed: false,
    justCompleted: true,
  }
}
