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
 * Shared WebSocket reconnect-notification primitive.
 *
 * Events published while the WS is disconnected (backend restart,
 * network blip, browser sleep) are dropped — the socket has no replay
 * buffer. The only way a stateful UI recovers from a missed event is to
 * refetch state from REST on reconnect. This module provides the hook
 * point so each consumer can wire its own reseed callback without
 * spawning its own timer or watching the socket lifecycle manually.
 *
 * Implementation: event-driven, NOT polled. `socket.ts` dispatches a
 * ``bodhiorchard:socket-reconnected`` event on every successful WS
 * ``onopen`` after the first one. We listen on the window and fan out
 * to every registered callback. This catches sub-second restart
 * windows that a 5 s polling timer would miss — common when the
 * backend restart is fast (the user observed banner-stuck after a
 * restart where the WS reconnected within the same second).
 *
 * Usage:
 *
 *     import { onSocketReconnect } from '@/services/wsReconnect'
 *
 *     const unregister = onSocketReconnect(async () => {
 *       // Re-seed local state from REST — events during the gap are lost.
 *       await store.fetch()
 *     })
 *
 *     // Later, when the component unmounts / topic changes:
 *     unregister()
 */

type ReconnectCallback = () => void | Promise<void>

const callbacks: Set<ReconnectCallback> = new Set()
const RECONNECT_EVENT = 'bodhiorchard:socket-reconnected'

function fireAll(): void {
  // Snapshot so a callback that unregisters itself during the fire
  // doesn't mutate the iteration target. Each callback is awaited
  // independently — one bad callback throwing or rejecting must not
  // block the rest.
  const snapshot = Array.from(callbacks)
  for (const cb of snapshot) {
    try {
      const result = cb()
      if (result instanceof Promise) {
        result.catch((err) => {
          // eslint-disable-next-line no-console
          console.warn('[wsReconnect] callback rejected:', err)
        })
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[wsReconnect] callback threw:', err)
    }
  }
}

let listenerAttached = false

function ensureListener(): void {
  if (listenerAttached || typeof window === 'undefined') return
  window.addEventListener(RECONNECT_EVENT, fireAll)
  listenerAttached = true
}

/**
 * Register a callback fired once each time the WS reconnects (every
 * ``onopen`` after the initial connect). Returns an unregister
 * function — call it when the owning component / subscription tears
 * down so the callback set doesn't leak across navigations.
 *
 * The callback does NOT fire on the initial socket open after page
 * load — that's the page's own mount lifecycle, where the consumer's
 * initial fetch happens anyway. Only subsequent reconnects (backend
 * restart, network blip, tab wake-up) trigger the refetch.
 */
export function onSocketReconnect(callback: ReconnectCallback): () => void {
  callbacks.add(callback)
  ensureListener()
  return () => {
    callbacks.delete(callback)
  }
}
