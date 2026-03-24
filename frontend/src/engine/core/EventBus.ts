/**
 * EventBus — Type-safe pub/sub for decoupled engine communication.
 *
 * Uses TypeScript generics to enforce that:
 * 1. Event names must be keys of the EventMap
 * 2. Payloads must match the type declared for that event
 *
 * This prevents silent failures from typos (e.g., 'pick:clicks' vs 'pick:click').
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type EventCallback<T = any> = (payload: T) => void

/**
 * A type-safe event bus. Pass an interface mapping event names to payload types:
 *
 * ```ts
 * interface MyEvents {
 *   'scene:ready': void
 *   'scene:resize': { width: number; height: number }
 * }
 * const bus = new EventBus<MyEvents>()
 * bus.emit('scene:ready')         // OK
 * bus.emit('scene:readyy')        // TS error — typo caught at compile time
 * bus.emit('scene:resize', { width: 100, height: 200 }) // OK
 * bus.emit('scene:resize', 'wrong')  // TS error — wrong payload type
 * ```
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export class EventBus<EventMap extends Record<string, any> = Record<string, any>> {
  private listeners = new Map<string, Set<EventCallback>>()

  on<K extends string & keyof EventMap>(
    event: K,
    callback: EventCallback<EventMap[K]>,
  ): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)!.add(callback as EventCallback)
  }

  off<K extends string & keyof EventMap>(
    event: K,
    callback: EventCallback<EventMap[K]>,
  ): void {
    this.listeners.get(event)?.delete(callback as EventCallback)
  }

  emit<K extends string & keyof EventMap>(
    event: K,
    ...args: EventMap[K] extends void ? [] : [payload: EventMap[K]]
  ): void {
    const callbacks = this.listeners.get(event)
    if (callbacks) {
      const payload = args[0]
      for (const cb of callbacks) {
        cb(payload)
      }
    }
  }

  once<K extends string & keyof EventMap>(
    event: K,
    callback: EventCallback<EventMap[K]>,
  ): void {
    const wrapper: EventCallback<EventMap[K]> = (payload) => {
      this.off(event, wrapper)
      callback(payload)
    }
    this.on(event, wrapper)
  }

  clear(): void {
    this.listeners.clear()
  }
}
