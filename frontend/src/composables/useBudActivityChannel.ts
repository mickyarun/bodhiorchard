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

// Live updates for the open BUD: webhook-driven activity (PR opened,
// merged, commented, learning recorded) on `bud:<id>:activity`, plus a
// resync whenever the socket reconnects, since events that land while
// disconnected aren't buffered.

import { onUnmounted } from 'vue'
import { subscribe, unsubscribe } from '@/services/socket'
import { onSocketReconnect } from '@/services/wsReconnect'

export interface BudActivityHandlers {
  /** Refetch the BUD's state; runs on every event and on reconnect. */
  refresh: (budId: string) => void
  /** Runs when an event says the post-close learning recap was recorded. */
  onLearningRecorded: () => void
}

export function useBudActivityChannel(handlers: BudActivityHandlers) {
  let cleanup: (() => void) | null = null
  // Set on unmount: a load that finishes after the page has gone must not
  // subscribe again, or the subscription would never be dropped.
  let disposed = false

  function disconnect(): void {
    cleanup?.()
    cleanup = null
  }

  /** Follow one BUD, dropping whichever BUD was followed before. No-op once unmounted. */
  function connect(budId: string): void {
    disconnect()
    if (disposed) return
    const topic = `bud:${budId}:activity`
    const refresh = () => handlers.refresh(budId)
    const onEvent = (data: unknown) => {
      refresh()
      if ((data as { event_type?: string } | undefined)?.event_type === 'learning_recorded') {
        handlers.onLearningRecorded()
      }
    }
    subscribe(topic, onEvent)
    const unregisterReconnect = onSocketReconnect(refresh)
    cleanup = () => {
      unsubscribe(topic, onEvent)
      unregisterReconnect()
    }
  }

  onUnmounted(() => {
    disposed = true
    disconnect()
  })

  return { connect, disconnect }
}
