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
 * Singleton WebSocket manager for multiplexed real-time communication.
 *
 * Maintains a single WS connection per browser tab. Components subscribe
 * to string topics (e.g. "job:abc-123"); the server pushes events to
 * matching subscribers.
 *
 * Reconnects automatically with exponential backoff, and re-subscribes
 * all active topics after reconnect. Falls back gracefully — callers
 * can check `isConnected()` and use polling if WS is unavailable.
 */

const TOKEN_KEY = 'bodhiorchard_token'
/**
 * Max consecutive failed reconnects before backing off to the watchdog
 * cadence. Raised from 5 → 15 so a routine backend-restart window
 * (2s+4s+8s+15s*11 ≈ 3 min) is handled without user interaction.
 */
const MAX_RETRIES = 15
const BASE_DELAY_MS = 2000
/** Cap the exponential backoff delay so we don't wait 30s between tries. */
const MAX_DELAY_MS = 15000
/**
 * Watchdog cadence — after retries are exhausted we still probe every
 * WATCHDOG_INTERVAL_MS so the socket recovers from long restarts
 * without relying on the user flipping tabs.
 */
const WATCHDOG_INTERVAL_MS = 30000

// ── Module state ─────────────────────────────────────────────────
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let watchdogTimer: ReturnType<typeof setInterval> | null = null
let retryCount = 0
let _dead = false // true after all retries exhausted (until watchdog/visibility resets it)
/** True once the WS has opened successfully at least once. Drives the
 *  ``bodhiorchard:socket-reconnected`` event below — the very first
 *  ``onopen`` is the initial connect, not a reconnect, so consumers that
 *  re-seed REST state shouldn't fire on it. */
let _hasEverOpened = false

/** topic → set of callbacks */
const listeners: Map<string, Set<(data: unknown) => void>> = new Map()

// ── Helpers ──────────────────────────────────────────────────────

function buildWsUrl(): string {
  const token = localStorage.getItem(TOKEN_KEY)
  const loc = window.location
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${loc.host}/api/v1/ws?token=${encodeURIComponent(token ?? '')}`
}

function clearReconnectTimer(): void {
  if (reconnectTimer !== null) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function scheduleReconnect(): void {
  if (retryCount >= MAX_RETRIES) {
    // Mark dead but keep the watchdog running — if the backend eventually
    // comes back, the watchdog will reset state and try again.
    _dead = true
    ensureWatchdog()
    return
  }
  const delay = Math.min(BASE_DELAY_MS * Math.pow(2, retryCount), MAX_DELAY_MS)
  retryCount++
  reconnectTimer = setTimeout(() => connect(), delay)
}

/**
 * Periodically retry while dead. Survives the scenario where the user
 * stays on the tab during a backend restart longer than MAX_RETRIES —
 * no visibility/online event fires, so without this the socket never
 * recovers. Cheap: one fetch-free probe every 30s.
 */
function ensureWatchdog(): void {
  if (watchdogTimer !== null) return
  watchdogTimer = setInterval(() => {
    if (listeners.size === 0) return // nothing cares — skip
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return // already alive — skip
    }
    // Fresh attempt: reset state and retry from the top of the backoff ramp.
    retryCount = 0
    _dead = false
    connect()
  }, WATCHDOG_INTERVAL_MS)
}

/** Re-send subscribe messages for all active topics after reconnect. */
function resubscribeAll(): void {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  for (const topic of listeners.keys()) {
    ws.send(JSON.stringify({ action: 'subscribe', topic }))
  }
}

// ── Public API ───────────────────────────────────────────────────

export function connect(): void {
  // Don't open a second connection
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return
  }

  clearReconnectTimer()
  const url = buildWsUrl()

  try {
    ws = new WebSocket(url)
  } catch {
    scheduleReconnect()
    return
  }

  ws.onopen = () => {
    retryCount = 0
    _dead = false
    resubscribeAll()
    // Fire a custom event on EVERY open after the first. Consumers
    // (see `wsReconnect.onSocketReconnect`) use this to refetch state
    // they may have missed while the socket was dropped — events
    // emitted during the gap are not buffered server-side. Skipping
    // the very first open keeps the contract "reconnect" not "initial
    // connect" so refetch callbacks don't double-fire on page load.
    if (_hasEverOpened) {
      window.dispatchEvent(new CustomEvent('bodhiorchard:socket-reconnected'))
    }
    _hasEverOpened = true
  }

  ws.onmessage = (event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data as string) as Record<string, unknown>
      if (msg.topic && typeof msg.topic === 'string') {
        const topicListeners = listeners.get(msg.topic)
        topicListeners?.forEach((cb) => cb(msg.data))
      }
      // Ignore pong / other control messages
    } catch {
      // Non-JSON frame — ignore
    }
  }

  ws.onclose = (ev: CloseEvent) => {
    ws = null
    // 4001 = auth failure (expired / invalid JWT). Retrying with the
    // same token is pointless; kick the axios refresh interceptor by
    // pinging an authenticated endpoint. On success, axios dispatches
    // `bodhiorchard:token-refreshed` and the window listener below
    // reconnects us with the fresh token.
    if (ev.code === 4001) {
      _dead = true
      triggerTokenRefresh()
      return
    }
    scheduleReconnect()
  }

  ws.onerror = () => {
    // onclose will fire after this — reconnect handled there
  }
}

export function disconnect(): void {
  clearReconnectTimer()
  if (watchdogTimer !== null) {
    clearInterval(watchdogTimer)
    watchdogTimer = null
  }
  _dead = true
  if (ws) {
    ws.onclose = null // prevent reconnect
    ws.close()
    ws = null
  }
}

/**
 * Subscribe to a topic. Triggers `connect()` lazily on first call.
 *
 * Multiple callbacks can be registered per topic; only one server-side
 * subscription is maintained (deduplication).
 */
export function subscribe(topic: string, callback: (data: unknown) => void): void {
  const isNew = !listeners.has(topic)
  const set = listeners.get(topic) ?? new Set()
  set.add(callback)
  listeners.set(topic, set)

  // Lazy connect
  if (!ws || ws.readyState === WebSocket.CLOSED) {
    _dead = false
    retryCount = 0
    connect()
  } else if (isNew && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: 'subscribe', topic }))
  }
}

/**
 * Remove a callback. If no listeners remain for the topic, sends an
 * unsubscribe message to the server.
 */
export function unsubscribe(topic: string, callback: (data: unknown) => void): void {
  const set = listeners.get(topic)
  if (!set) return
  set.delete(callback)
  if (set.size === 0) {
    listeners.delete(topic)
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ action: 'unsubscribe', topic }))
    }
  }
}

export function isConnected(): boolean {
  return ws !== null && ws.readyState === WebSocket.OPEN
}

export function isDead(): boolean {
  return _dead
}

// ── Network / visibility recovery ────────────────────────────────

function attemptReconnect(): void {
  if (ws && ws.readyState === WebSocket.OPEN) return
  if (listeners.size === 0) return // nothing to reconnect for
  retryCount = 0
  _dead = false
  connect()
}

/**
 * Fire a single authenticated REST call to let the axios refresh
 * interceptor observe 401 and rotate the JWT. The subsequent
 * `bodhiorchard:token-refreshed` event (dispatched by api.ts) drives
 * the window listener below to reconnect. Safe to call even when the
 * token is still valid — the response is ignored.
 */
function triggerTokenRefresh(): void {
  // Dynamic import avoids a circular `socket ↔ api` import at module load.
  import('@/services/api')
    .then(({ default: api }) => api.get('/v1/auth/me').catch(() => { /* swallow */ }))
    .catch(() => { /* axios not available — user has to re-login manually */ })
}

if (typeof window !== 'undefined') {
  window.addEventListener('online', attemptReconnect)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      attemptReconnect()
    }
  })
  // When the axios interceptor rotates the JWT, drop the stale socket
  // and reconnect using the fresh token on the next connect().
  window.addEventListener('bodhiorchard:token-refreshed', () => {
    if (ws) {
      ws.onclose = null // prevent the pending-close from looping us
      ws.close()
      ws = null
    }
    clearReconnectTimer()
    retryCount = 0
    _dead = false
    if (listeners.size > 0) connect()
  })
}
