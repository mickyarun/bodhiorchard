// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * RaceRegistry — in-memory coupling between OrgRoom and RaceRoom.
 *
 * When OrgRoom creates a RaceRoom it needs to know when that RaceRoom
 * disposes, so it can remove the `ActiveRaceSummary` entry from its
 * schema. Colyseus rooms run in the same process in our deployment, so
 * a simple module-local `Map` of "roomId → dispose callback" works
 * without reaching for Redis or presence pub/sub.
 *
 * If we ever scale beyond one Colyseus node, this module becomes the
 * right seam to swap for a Redis / presence-based channel — every caller
 * goes through `registerRaceDisposeCallback` / `fireRaceDispose`.
 */

type DisposeCallback = () => void
type PhaseCallback = (phase: string) => void

interface RoomHooks {
  onDispose: DisposeCallback
  onPhase: PhaseCallback
}

const hooks = new Map<string, RoomHooks>()

/**
 * Register dispose + phase-change callbacks for a race room. Overwrites
 * any prior registration for the same roomId (only one OrgRoom should
 * register per race; replacing is the right failure mode if a second
 * one ever tries).
 */
export function registerRaceHooks(roomId: string, cbs: RoomHooks): void {
  hooks.set(roomId, cbs)
}

/**
 * Invoke + remove the callbacks registered for this roomId. Called by
 * RaceRoom.onDispose. Safe to call even if no callback is registered.
 */
export function fireRaceDispose(roomId: string): void {
  const pair = hooks.get(roomId)
  if (!pair) return
  hooks.delete(roomId)
  try {
    pair.onDispose()
  } catch (err) {
    console.error(`[RaceRegistry] dispose callback for room ${roomId} threw:`, err)
  }
}

/**
 * Invoke the phase-change callback for this roomId. Does NOT remove the
 * registration — phases transition multiple times (`countdown → running →
 * finished`), and dispose still needs to clean up afterwards.
 */
export function fireRacePhase(roomId: string, phase: string): void {
  const pair = hooks.get(roomId)
  if (!pair) return
  try {
    pair.onPhase(phase)
  } catch (err) {
    console.error(`[RaceRegistry] phase callback for room ${roomId} threw:`, err)
  }
}
