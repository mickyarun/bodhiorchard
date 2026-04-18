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
const MAX_RETRIES = 5
const BASE_DELAY_MS = 2000

// ── Module state ─────────────────────────────────────────────────
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let retryCount = 0
let _dead = false // true after all retries exhausted (until network/visibility resets it)

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
    _dead = true
    return
  }
  const delay = BASE_DELAY_MS * Math.pow(2, retryCount)
  retryCount++
  reconnectTimer = setTimeout(() => connect(), delay)
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
    // 4001 = auth failure — don't retry
    if (ev.code === 4001) {
      _dead = true
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

if (typeof window !== 'undefined') {
  window.addEventListener('online', attemptReconnect)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      attemptReconnect()
    }
  })
}
