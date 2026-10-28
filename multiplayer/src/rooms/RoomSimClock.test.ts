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
 * The race and minigame simulation loops must run on the room clock. Colyseus
 * only routes the room clock's timers through `onUncaughtException`, so a
 * throwing tick on a bare Node `setInterval` would still exit the process, and
 * a bare interval also outlives the room because dispose only clears the
 * room clock.
 */
import type { Client, Room } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { MinigameRoom } from "./MinigameRoom"
import { RaceRoom } from "./RaceRoom"

const TICK_STEP_MS = 100
let errorSpy: ReturnType<typeof vi.spyOn>

/** Number of timers still scheduled on the room's own clock. */
function activeClockTimers(room: Room): number {
  const { delayed } = room.clock as unknown as { delayed: { active: boolean }[] }
  return delayed.filter((d) => d.active).length
}

/** Advance the room clock by one step, as the room's patch loop would. */
function tickRoomClock(room: Room): void {
  room.clock.currentTime -= TICK_STEP_MS
  room.clock.tick()
}

function fakeClient(sessionId: string): Client {
  return { sessionId, userData: undefined, send: vi.fn() } as unknown as Client
}

function expectReportedTimerError(): void {
  expect(errorSpy).toHaveBeenCalledTimes(1)
  const [format, , , method, message] = errorSpy.mock.calls[0] as unknown[]
  expect(format).toContain("uncaught error")
  expect(method).toBe("setInterval")
  expect(message).toBe("tick bug")
}

beforeEach(() => {
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
  errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("RaceRoom simulation loop", () => {
  function runningRace(): RaceRoom {
    const room = new RaceRoom()
    room.onCreate({ orgId: "org-a", hostUserId: "alice", hostName: "Alice", distanceM: 100 })
    ;(room as unknown as { beginRunning(): void }).beginRunning()
    return room
  }

  it("schedules the sim tick on the room clock", () => {
    const room = new RaceRoom()
    room.onCreate({ orgId: "org-a", hostUserId: "alice", hostName: "Alice", distanceM: 100 })
    const before = activeClockTimers(room)

    ;(room as unknown as { beginRunning(): void }).beginRunning()

    expect(activeClockTimers(room)).toBe(before + 1)
    room.clock.clear()
  })

  it("reports a throwing sim tick instead of letting it escape", () => {
    const room = runningRace()
    vi.spyOn(room as unknown as { simStep(): void }, "simStep").mockImplementation(() => {
      throw new Error("tick bug")
    })

    expect(() => tickRoomClock(room)).not.toThrow()

    expectReportedTimerError()
    room.clock.clear()
  })

  it("stops ticking once the room clock is cleared on dispose", () => {
    vi.useFakeTimers()
    const room = runningRace()
    const simStep = vi.spyOn(room as unknown as { simStep(): void }, "simStep")

    room.clock.clear()
    tickRoomClock(room)
    vi.advanceTimersByTime(TICK_STEP_MS * 10)

    expect(simStep).not.toHaveBeenCalled()
  })
})

describe("MinigameRoom simulation loop", () => {
  function playingPollenPop(): MinigameRoom {
    const room = new MinigameRoom()
    room.onCreate({ game: "pollen_pop" })
    room.onJoin(fakeClient("s-alice"), { userId: "alice", name: "Alice", orgId: "org-a" })
    return room
  }

  it("schedules the engine tick on the room clock and clears it when the game ends", () => {
    const room = new MinigameRoom()
    room.onCreate({ game: "pollen_pop" })
    const before = activeClockTimers(room)

    room.onJoin(fakeClient("s-alice"), { userId: "alice", name: "Alice", orgId: "org-a" })
    const afterJoin = activeClockTimers(room)
    ;(room as unknown as { stopSim(): void }).stopSim()

    expect(afterJoin).toBeGreaterThan(before)
    expect(activeClockTimers(room)).toBeLessThan(afterJoin)
    room.clock.clear()
  })

  it("reports a throwing engine tick instead of letting it escape", () => {
    const room = playingPollenPop()
    const engine = (room as unknown as { engine: { tick(): void } }).engine
    vi.spyOn(engine, "tick").mockImplementation(() => {
      throw new Error("tick bug")
    })

    expect(() => tickRoomClock(room)).not.toThrow()

    expectReportedTimerError()
    room.clock.clear()
  })
})
