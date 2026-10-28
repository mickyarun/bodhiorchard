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
 * In-process registries that couple OrgRoom summaries to their child race /
 * backlash rooms: lifecycle (dispose once, phase repeatedly) and fault
 * containment (a throwing hook must not break the caller).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  fireRaceDispose,
  fireRaceInviteDeclined,
  fireRacePhase,
  registerRaceHooks,
} from "./RaceRegistry"
import {
  fireBacklashDispose,
  fireBacklashPhase,
  fireBacklashViewers,
  registerBacklashSummaryHooks,
} from "./BacklashRegistry"

let errorSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("RaceRegistry", () => {
  it("fires phase changes repeatedly and dispose exactly once", () => {
    const hooks = { onDispose: vi.fn(), onPhase: vi.fn() }
    registerRaceHooks("race-a", hooks)

    fireRacePhase("race-a", "countdown")
    fireRacePhase("race-a", "running")
    fireRaceDispose("race-a")
    fireRaceDispose("race-a")
    fireRacePhase("race-a", "finished")

    expect(hooks.onPhase.mock.calls).toEqual([["countdown"], ["running"]])
    expect(hooks.onDispose).toHaveBeenCalledTimes(1)
  })

  it("ignores events for rooms that never registered", () => {
    expect(() => {
      fireRacePhase("ghost", "running")
      fireRaceInviteDeclined("ghost", "u1")
      fireRaceDispose("ghost")
    }).not.toThrow()
  })

  it("treats a missing decline hook as a no-op", () => {
    registerRaceHooks("race-b", { onDispose: vi.fn(), onPhase: vi.fn() })
    expect(() => fireRaceInviteDeclined("race-b", "u1")).not.toThrow()
    fireRaceDispose("race-b")
  })

  it("keeps the registration after a decline so later declines still arrive", () => {
    const onInviteeDeclined = vi.fn()
    registerRaceHooks("race-c", { onDispose: vi.fn(), onPhase: vi.fn(), onInviteeDeclined })

    fireRaceInviteDeclined("race-c", "u1")
    fireRaceInviteDeclined("race-c", "u2")

    expect(onInviteeDeclined.mock.calls).toEqual([["u1"], ["u2"]])
    fireRaceDispose("race-c")
  })

  it("contains a throwing hook and logs the room id without newlines", () => {
    registerRaceHooks("race\nforged", {
      onDispose: () => {
        throw new Error("dispose failed")
      },
      onPhase: () => {
        throw new Error("phase failed")
      },
      onInviteeDeclined: () => {
        throw new Error("decline failed")
      },
    })

    expect(() => fireRacePhase("race\nforged", "running")).not.toThrow()
    expect(() => fireRaceInviteDeclined("race\nforged", "u1")).not.toThrow()
    expect(() => fireRaceDispose("race\nforged")).not.toThrow()
    expect(errorSpy).toHaveBeenCalledTimes(3)
    for (const call of errorSpy.mock.calls) {
      expect(String(call[1])).toContain("forged")
      expect(String(call[1])).not.toMatch(/[\r\n]/)
    }
  })

  it("lets a second registration for the same room replace the first", () => {
    const first = { onDispose: vi.fn(), onPhase: vi.fn() }
    const second = { onDispose: vi.fn(), onPhase: vi.fn() }
    registerRaceHooks("race-d", first)
    registerRaceHooks("race-d", second)

    fireRaceDispose("race-d")

    expect(first.onDispose).not.toHaveBeenCalled()
    expect(second.onDispose).toHaveBeenCalledTimes(1)
  })
})

describe("BacklashRegistry summary hooks", () => {
  it("relays phase and viewer changes until the room disposes", () => {
    const hooks = { onDispose: vi.fn(), onPhase: vi.fn(), onViewers: vi.fn() }
    registerBacklashSummaryHooks("bl-a", hooks)

    fireBacklashPhase("bl-a", "playing")
    fireBacklashViewers("bl-a", ["Sam", "Ana"])
    fireBacklashDispose("bl-a")
    fireBacklashPhase("bl-a", "finished")
    fireBacklashDispose("bl-a")

    expect(hooks.onPhase.mock.calls).toEqual([["playing"]])
    expect(hooks.onViewers).toHaveBeenCalledWith(["Sam", "Ana"])
    expect(hooks.onDispose).toHaveBeenCalledTimes(1)
  })

  it("contains a throwing summary hook", () => {
    registerBacklashSummaryHooks("bl-b", {
      onDispose: () => {
        throw new Error("dispose failed")
      },
      onPhase: () => {
        throw new Error("phase failed")
      },
      onViewers: () => {
        throw new Error("viewers failed")
      },
    })

    expect(() => fireBacklashPhase("bl-b", "playing")).not.toThrow()
    expect(() => fireBacklashViewers("bl-b", [])).not.toThrow()
    expect(() => fireBacklashDispose("bl-b")).not.toThrow()
    expect(errorSpy).toHaveBeenCalledTimes(3)
  })
})
