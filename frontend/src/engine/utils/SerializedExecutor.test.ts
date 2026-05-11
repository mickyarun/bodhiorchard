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
 * Unit tests for SerializedExecutor.
 *
 * These tests use a "controlled promise" helper instead of fake timers because
 * we want to assert exact ordering between submits, runner invocations, and
 * resolutions. Fake timers would obscure that with virtual time.
 *
 * Test naming convention: each test name describes the OBSERVABLE behavior,
 * not the implementation. If the internal pending/running fields are renamed
 * tomorrow, these tests should still pass unchanged.
 */
import { describe, it, expect, vi } from 'vitest'
import { SerializedExecutor, type SerializedRunner } from './SerializedExecutor'

/**
 * Creates a promise that can be resolved or rejected externally.
 * Lets a test "hold" the runner mid-execution until the test decides to release it.
 */
function deferred<T = void>(): {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (err: unknown) => void
} {
  let resolve!: (value: T) => void
  let reject!: (err: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('SerializedExecutor', () => {
  describe('single submit', () => {
    it('invokes the runner once with the submitted input', async () => {
      const runner = vi.fn<Parameters<SerializedRunner<string>>, ReturnType<SerializedRunner<string>>>(
        async () => {},
      )
      const executor = new SerializedExecutor<string>(runner)

      await executor.submit('hello')

      expect(runner).toHaveBeenCalledTimes(1)
      expect(runner.mock.calls[0][0]).toBe('hello')
      // Second arg is the AbortSignal — assert it's an AbortSignal instance
      expect(runner.mock.calls[0][1]).toBeInstanceOf(AbortSignal)
    })

    it('resolves the submit promise only after the runner completes', async () => {
      const gate = deferred<void>()
      const order: string[] = []
      const executor = new SerializedExecutor<string>(async () => {
        order.push('runner-start')
        await gate.promise
        order.push('runner-end')
      })

      const submitP = executor.submit('x').then(() => order.push('submit-resolved'))
      // Microtask flush — runner should have started but not yet finished
      await Promise.resolve()
      expect(order).toEqual(['runner-start'])

      gate.resolve()
      await submitP

      expect(order).toEqual(['runner-start', 'runner-end', 'submit-resolved'])
    })
  })

  describe('coalescing — latest wins', () => {
    it('drops intermediate submits while the runner is busy', async () => {
      const gateA = deferred<void>()
      const gateC = deferred<void>()
      const seenInputs: string[] = []
      const executor = new SerializedExecutor<string>(async (input) => {
        seenInputs.push(input)
        if (input === 'A') await gateA.promise
        if (input === 'C') await gateC.promise
      })

      // Submit A — starts running, blocks on gateA
      const pA = executor.submit('A')
      await Promise.resolve() // let the runner start
      expect(seenInputs).toEqual(['A'])

      // While A is running, submit B then C — only C should be kept
      const pB = executor.submit('B')
      const pC = executor.submit('C')

      // Release A — drain loop should now pick up the LATEST pending value (C),
      // not B (which was overwritten by C in the pending slot).
      gateA.resolve()
      await Promise.resolve()
      await Promise.resolve()
      expect(seenInputs).toEqual(['A', 'C'])

      // Release C — all three submit promises resolve together
      gateC.resolve()
      await Promise.all([pA, pB, pC])
      expect(seenInputs).toEqual(['A', 'C'])
    })

    it('all concurrent submit() promises resolve once the drain is empty', async () => {
      const gate = deferred<void>()
      const executor = new SerializedExecutor<number>(async () => {
        await gate.promise
      })

      const order: string[] = []
      const p1 = executor.submit(1).then(() => order.push('p1'))
      const p2 = executor.submit(2).then(() => order.push('p2'))
      const p3 = executor.submit(3).then(() => order.push('p3'))

      // None should resolve until the runner releases
      await Promise.resolve()
      expect(order).toEqual([])

      gate.resolve()
      await Promise.all([p1, p2, p3])
      // All three resolve in submit order (FIFO over the same promise chain)
      expect(order).toEqual(['p1', 'p2', 'p3'])
    })
  })

  describe('error handling', () => {
    it('captures runner exceptions in lastError without rejecting submit', async () => {
      const consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {})
      const boom = new Error('runner blew up')
      const executor = new SerializedExecutor<string>(async () => {
        throw boom
      })

      // Should NOT reject — error swallowing is intentional
      await expect(executor.submit('x')).resolves.toBeUndefined()
      expect(executor.lastError).toBe(boom)
      expect(consoleErr).toHaveBeenCalled()
      consoleErr.mockRestore()
    })

    it('clears lastError on the next successful run', async () => {
      const consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {})
      let shouldThrow = true
      const executor = new SerializedExecutor<string>(async () => {
        if (shouldThrow) throw new Error('first call fails')
      })

      await executor.submit('first')
      expect(executor.lastError).toBeInstanceOf(Error)

      shouldThrow = false
      await executor.submit('second')
      expect(executor.lastError).toBeNull()
      consoleErr.mockRestore()
    })

    it('continues draining after an error so the latest data still gets applied', async () => {
      const consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {})
      const seen: string[] = []
      const gate = deferred<void>()
      const executor = new SerializedExecutor<string>(async (input) => {
        seen.push(input)
        if (input === 'A') {
          await gate.promise
          throw new Error('A fails')
        }
        // B and C succeed
      })

      const pA = executor.submit('A')
      await Promise.resolve()
      executor.submit('B')
      executor.submit('C') // B is dropped, C is kept
      gate.resolve()
      await pA

      // A failed but C still got applied — observable proof that error
      // swallowing keeps the latest data flowing
      expect(seen).toEqual(['A', 'C'])
      expect(executor.lastError).toBeNull() // C's success cleared the A error
      consoleErr.mockRestore()
    })
  })

  describe('disposal', () => {
    it('aborts the in-flight runner via its AbortSignal', async () => {
      const gate = deferred<void>()
      let receivedSignal: AbortSignal | null = null
      const executor = new SerializedExecutor<string>(async (_input, signal) => {
        receivedSignal = signal
        await gate.promise
      })

      const p = executor.submit('x')
      await Promise.resolve()
      expect(receivedSignal).not.toBeNull()
      expect(receivedSignal!.aborted).toBe(false)

      executor.dispose()
      expect(receivedSignal!.aborted).toBe(true)

      // Release the gate so the runner returns
      gate.resolve()
      await p
    })

    it('makes submit() a no-op after disposal', async () => {
      const runner = vi.fn(async () => {})
      const executor = new SerializedExecutor<string>(runner)
      executor.dispose()

      await executor.submit('after-dispose')
      expect(runner).not.toHaveBeenCalled()
      expect(executor.isDisposed).toBe(true)
    })

    it('exits the drain loop on next iteration after disposal', async () => {
      const consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {})
      const gateA = deferred<void>()
      const seen: string[] = []
      const executor = new SerializedExecutor<string>(async (input) => {
        seen.push(input)
        if (input === 'A') await gateA.promise
      })

      const pA = executor.submit('A')
      await Promise.resolve()

      // Queue a B that should NEVER run because we'll dispose before A finishes
      executor.submit('B')
      executor.dispose()

      gateA.resolve()
      await pA

      expect(seen).toEqual(['A'])
      consoleErr.mockRestore()
    })

    it('is idempotent — calling dispose twice is safe', () => {
      const executor = new SerializedExecutor<string>(async () => {})
      expect(() => {
        executor.dispose()
        executor.dispose()
        executor.dispose()
      }).not.toThrow()
      expect(executor.isDisposed).toBe(true)
    })

    it('does not log AbortError as a runner failure', async () => {
      const consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {})
      const gate = deferred<void>()
      const executor = new SerializedExecutor<string>(async (_input, signal) => {
        await gate.promise
        // Runner respects the signal — throws AbortError on dispose
        signal.throwIfAborted()
      })

      const p = executor.submit('x')
      await Promise.resolve()
      executor.dispose()
      gate.resolve()
      await p

      // The AbortError must NOT pollute console.error — it's expected
      // disposal noise, not a real failure.
      expect(consoleErr).not.toHaveBeenCalled()
      consoleErr.mockRestore()
    })
  })

  describe('onDrained callback', () => {
    it('fires exactly once after a single submit completes', async () => {
      const onDrained = vi.fn()
      const executor = new SerializedExecutor<string>(async () => {}, { onDrained })

      await executor.submit('x')
      expect(onDrained).toHaveBeenCalledTimes(1)
    })

    it('fires once per drain burst, not per iteration (coalescing)', async () => {
      const onDrained = vi.fn()
      const gateA = deferred<void>()
      const seen: string[] = []
      const executor = new SerializedExecutor<string>(
        async (input) => {
          seen.push(input)
          if (input === 'A') await gateA.promise
        },
        { onDrained },
      )

      const pA = executor.submit('A')
      await Promise.resolve()
      // While A is running, queue B then C — C wins coalescing
      executor.submit('B')
      executor.submit('C')

      gateA.resolve()
      await pA

      // Two iterations ran (A and C), but onDrained fires ONCE at the end
      expect(seen).toEqual(['A', 'C'])
      expect(onDrained).toHaveBeenCalledTimes(1)
    })

    it('does not fire on disposal — only on natural drain', async () => {
      const onDrained = vi.fn()
      const gate = deferred<void>()
      const executor = new SerializedExecutor<string>(
        async () => { await gate.promise },
        { onDrained },
      )

      const p = executor.submit('x')
      await Promise.resolve()
      executor.dispose()
      gate.resolve()
      await p

      expect(onDrained).not.toHaveBeenCalled()
    })

    it('does not fire if every iteration failed (no successful runs)', async () => {
      const consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {})
      const onDrained = vi.fn()
      const executor = new SerializedExecutor<string>(
        async () => { throw new Error('always fails') },
        { onDrained },
      )

      await executor.submit('x')
      expect(onDrained).not.toHaveBeenCalled()
      consoleErr.mockRestore()
    })

    it('catches exceptions thrown by onDrained itself', async () => {
      const consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {})
      const executor = new SerializedExecutor<string>(
        async () => {},
        { onDrained: () => { throw new Error('callback boom') } },
      )

      // submit() must not reject even if onDrained throws
      await expect(executor.submit('x')).resolves.toBeUndefined()
      expect(consoleErr).toHaveBeenCalled()
      consoleErr.mockRestore()
    })
  })

  describe('lastError does not capture AbortError', () => {
    it('leaves lastError null after disposal-driven abort', async () => {
      const gate = deferred<void>()
      const executor = new SerializedExecutor<string>(async (_input, signal) => {
        await gate.promise
        signal.throwIfAborted()
      })

      const p = executor.submit('x')
      await Promise.resolve()
      executor.dispose()
      gate.resolve()
      await p

      // Critical: lastError must NOT be the AbortError. Upstream UI relies
      // on `if (engine.lastBuildError)` not firing on every navigation.
      expect(executor.lastError).toBeNull()
    })
  })

  describe('isRunning state', () => {
    it('reports isRunning correctly across the runner lifetime', async () => {
      const gate = deferred<void>()
      const executor = new SerializedExecutor<string>(async () => {
        await gate.promise
      })

      expect(executor.isRunning).toBe(false)
      const p = executor.submit('x')
      await Promise.resolve()
      expect(executor.isRunning).toBe(true)

      gate.resolve()
      await p
      expect(executor.isRunning).toBe(false)
    })
  })
})
