// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * SerializedExecutor — coalesced async work queue for "latest input wins" semantics.
 *
 * Use this when you have async work that must NOT run concurrently and where
 * intermediate inputs can be safely dropped if a newer one arrives. Examples:
 *   - Scene rebuilds where only the latest scene matters
 *   - Search-as-you-type queries where only the latest query matters
 *   - Persistence layers where only the latest state needs to be saved
 *
 * Guarantees:
 *   - At most ONE runner invocation is in-flight at any time.
 *   - When `submit(input)` is called while a runner is busy, `input` is queued
 *     as `pending`. If multiple submits stack up, only the LATEST is kept;
 *     earlier values are silently dropped (coalescing).
 *   - Every `submit()` caller's promise resolves only after the drain loop
 *     reaches a state where `pending === null` AND no runner is active.
 *     This means: when your `await submit(x)` resumes, the executor is fully
 *     idle and the most-recent input has been applied.
 *   - The runner is always invoked with a fresh `AbortSignal` for the
 *     CURRENT iteration. Calling `dispose()` aborts the in-flight signal so
 *     the runner can exit early.
 *   - The runner's exceptions are caught, logged, and stored in `lastError`.
 *     The drain loop continues regardless — a transient failure on stale
 *     input must not block the latest input from being applied.
 *   - After `dispose()`, all subsequent `submit()` calls are no-ops that
 *     resolve immediately. The executor is one-way: dispose is terminal.
 *
 * The runner signature `(input, signal) => Promise<void>` is intentionally
 * minimal. The signal is the standard Web Platform `AbortSignal` so runners
 * can use `signal.throwIfAborted()`, `signal.aborted` checks, or pass it
 * along to `fetch()` and other AbortSignal-aware APIs.
 *
 * Thread safety: this class assumes single-threaded JS execution (the event
 * loop). It is NOT safe across Web Workers or SharedWorker boundaries.
 */

/** Function signature for the work the executor serializes. */
export type SerializedRunner<T> = (input: T, signal: AbortSignal) => Promise<void>

/** Optional config for SerializedExecutor — error logging label and post-drain hook. */
export interface SerializedExecutorOptions {
  /** Prefix for error logs. Defaults to "SerializedExecutor". */
  logLabel?: string
  /**
   * Called once after the drain loop empties — i.e., when the executor goes
   * from busy-with-N-queued-items to fully-idle. Useful for "do this once
   * after all coalesced work is applied" semantics, like rewiring callbacks
   * exactly once instead of per-iteration. NOT called on disposal.
   */
  onDrained?: () => void
}

export class SerializedExecutor<T> {
  /** Latest queued input — overwritten by every submit(), consumed by the drain loop. */
  private pending: T | null = null
  /** Promise of the currently-running drain loop, or null if idle. */
  private running: Promise<void> | null = null
  /** Disposal flag — once true, the executor is terminal and ignores new submits. */
  private _disposed = false
  /** AbortController for the CURRENT iteration's runner. Null when no runner is active. */
  private currentAbort: AbortController | null = null
  /** Most recent FAILURE error from the runner, or null. AbortErrors are NOT stored. */
  private _lastError: unknown = null
  /** True if at least one run succeeded since drain started — used to gate onDrained. */
  private hadSuccessThisDrain = false

  private readonly logLabel: string
  private readonly onDrained?: () => void

  /**
   * @param runner - Async work to perform. Receives the latest queued input
   *                 plus an `AbortSignal` that aborts when `dispose()` is called.
   * @param options - Optional logLabel + onDrained callback.
   *                  String form is also supported for back-compat: passing
   *                  a string is treated as `{ logLabel: ... }`.
   */
  constructor(
    private readonly runner: SerializedRunner<T>,
    options: SerializedExecutorOptions | string = {},
  ) {
    const opts = typeof options === 'string' ? { logLabel: options } : options
    this.logLabel = opts.logLabel ?? 'SerializedExecutor'
    this.onDrained = opts.onDrained
  }

  /** True if `dispose()` has been called. New submits are no-ops. */
  get isDisposed(): boolean { return this._disposed }

  /** True if the drain loop is currently running. */
  get isRunning(): boolean { return this.running !== null }

  /**
   * The error from the most recent FAILED runner invocation, or `null` if
   * the last invocation succeeded or was aborted. Cleared on every successful
   * run. AbortErrors are deliberately NOT stored here — disposal is a normal
   * lifecycle event, not a failure, so upstream UI checking
   * `if (executor.lastError) showToast(...)` won't fire spurious toasts on
   * navigation/cleanup.
   */
  get lastError(): unknown { return this._lastError }

  /**
   * Submit work to be executed. If a runner is already active, the input is
   * queued (replacing any previous pending value) and the caller awaits the
   * drain loop. The returned promise resolves once the executor is fully
   * idle — meaning the latest queued input has been processed.
   *
   * If `dispose()` has already been called, this is a no-op that resolves
   * immediately.
   */
  async submit(input: T): Promise<void> {
    if (this._disposed) return

    // Coalesce: latest input overwrites any previously queued one.
    this.pending = input

    // If a drain is already running, just await it. The drain will pick up
    // our queued input on its next iteration.
    if (this.running) {
      await this.running
      return
    }

    // No drain running — start one. Capturing the promise into `this.running`
    // BEFORE awaiting it is what allows concurrent submits to find and await
    // the in-flight loop.
    this.running = this.drain()
    try {
      await this.running
    } finally {
      this.running = null
    }
  }

  /**
   * Mark the executor as disposed. Aborts any in-flight runner via its
   * AbortSignal so it can exit early. Clears the pending queue. After
   * disposal, all `submit()` calls return immediately without invoking
   * the runner.
   *
   * Idempotent: calling dispose multiple times is safe.
   */
  dispose(): void {
    if (this._disposed) return
    this._disposed = true
    this.pending = null
    // Abort the current iteration's signal so a long-running runner can
    // bail out at its next await boundary.
    this.currentAbort?.abort()
    this.currentAbort = null
  }

  /**
   * The drain loop — pulls from `pending` and runs the runner until empty
   * or disposed. Each iteration creates its own AbortController so the
   * runner gets a fresh signal scoped to just that one iteration.
   *
   * After the loop exits naturally (pending empty, not disposed), fires
   * the `onDrained` callback exactly once if at least one run succeeded.
   * This lets callers do "rewire OrgRoom callbacks once after all queued
   * builds settled" without paying for it per iteration.
   */
  private async drain(): Promise<void> {
    this.hadSuccessThisDrain = false
    while (this.pending && !this._disposed) {
      const input = this.pending
      this.pending = null

      const controller = new AbortController()
      this.currentAbort = controller

      try {
        await this.runner(input, controller.signal)
        this._lastError = null
        this.hadSuccessThisDrain = true
      } catch (err) {
        if (isAbortError(err)) {
          // Disposal-driven abort — silent. Don't pollute lastError or logs.
          // The while-condition will exit on the next iteration.
        } else {
          console.error(`[${this.logLabel}] runner failed:`, err)
          this._lastError = err
        }
      } finally {
        // Only clear if it's still ours — a re-entrant dispose() may have
        // already cleared it (though that path is currently impossible
        // because dispose() doesn't await anything).
        if (this.currentAbort === controller) {
          this.currentAbort = null
        }
      }
    }

    // Drain emptied naturally (not via disposal) AND at least one iteration
    // succeeded → fire onDrained exactly once. The disposal path skips this
    // because callers shouldn't run "post-build wiring" against torn-down state.
    if (!this._disposed && this.hadSuccessThisDrain && this.onDrained) {
      try {
        this.onDrained()
      } catch (err) {
        console.error(`[${this.logLabel}] onDrained callback threw:`, err)
      }
    }
  }
}

/**
 * Detect a standard `AbortError` (DOMException with name === 'AbortError').
 * The Web Platform convention for abort propagation through async functions.
 */
function isAbortError(err: unknown): boolean {
  return (
    err instanceof DOMException && err.name === 'AbortError'
  ) || (
    typeof err === 'object' && err !== null && (err as { name?: string }).name === 'AbortError'
  )
}
