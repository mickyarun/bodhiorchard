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
 * Keeps the replies that replace ``currentBUD`` in the order they describe
 * the server, not the order they arrive in.
 *
 * A stage move that auto-assigns someone publishes agent-activity events
 * before the PATCH commits. The page refreshes on those events, so a GET
 * can read the old stage and land after the PATCH reply, putting the old
 * stage back on screen. Two rules stop that:
 *
 * - a refresh asked for while a write to the same BUD is in flight waits
 *   for the write to settle, so it reads the committed row;
 * - every reply carries a stamp (a read when it is sent, a write when it
 *   is answered) and is dropped if the BUD already shows a later one.
 */
export interface BudReplyOrder {
  /** Next stamp. Reads take one when sent, writes when answered. */
  stamp: () => number
  /** True (and records it) when a reply stamped ``at`` is newer than what ``id`` shows. */
  accept: (id: string, at: number) => boolean
  /** Run a write to ``id`` so refreshes of that BUD wait for it. */
  track: <T>(id: string, run: () => Promise<T>) => Promise<T>
  /** Resolves once no write to ``id`` is in flight. */
  settled: (id: string) => Promise<void>
}

export function createBudReplyOrder(): BudReplyOrder {
  let clock = 0
  let shown = { id: '', at: 0 }
  const writes = new Map<string, Set<Promise<unknown>>>()

  function stamp(): number {
    clock += 1
    return clock
  }

  function accept(id: string, at: number): boolean {
    if (shown.id === id && at < shown.at) return false
    shown = { id, at }
    return true
  }

  async function track<T>(id: string, run: () => Promise<T>): Promise<T> {
    const pending = run()
    const inFlight = writes.get(id) ?? new Set<Promise<unknown>>()
    inFlight.add(pending)
    writes.set(id, inFlight)
    try {
      return await pending
    } finally {
      inFlight.delete(pending)
      if (inFlight.size === 0) writes.delete(id)
    }
  }

  async function settled(id: string): Promise<void> {
    for (let inFlight = writes.get(id); inFlight; inFlight = writes.get(id)) {
      await Promise.allSettled([...inFlight])
    }
  }

  return { stamp, accept, track, settled }
}
