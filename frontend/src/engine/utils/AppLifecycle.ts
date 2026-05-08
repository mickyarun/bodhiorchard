// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Lifecycle hardening helpers shared across every `pc.Application`
 * instance in the codebase (GardenEngine, GraphEngine,
 * CharacterPreviewScene).
 *
 * All three previously had to grow these defenses independently —
 * extracting the shared shape avoids drift and ensures a fix in one
 * place propagates to all hosted PlayCanvas instances.
 */

import type * as pc from 'playcanvas'

/**
 * Install canvas-level WebGL context-loss / restore handlers.
 *
 * Browsers can release the WebGL context under memory pressure or after
 * long tab idle (Chrome especially). When this happens, every graphics
 * resource keeps its JS wrapper but loses its GPU-side `.impl`, and the
 * very next render attempt crashes inside `WebglGraphicsDevice.draw`
 * with `Cannot read properties of undefined (reading 'impl')` — once
 * per frame, forever.
 *
 * On `webglcontextlost`: `preventDefault()` (without it the canvas is
 * permanently dead) + `app.autoRender = false` so the doomed render
 * path can't fire again.
 *
 * On `webglcontextrestored`: full page reload. Rebuilding every
 * Texture / VertexBuffer / Shader in-place is invasive and error-prone;
 * the OrgRoom snapshot (or each engine's own bootstrap path) restores
 * scene state on the next boot, freshly uploaded to the new context.
 * Production users almost never hit context loss twice in a session,
 * so the reload cost is negligible.
 *
 * @param label included in console.warn so the source app is
 *   identifiable when multiple pc.Application instances coexist on
 *   the same page.
 * @returns cleanup function — detaches both listeners. Call from the
 *   host's destroy() so a teardown does not leave dangling listeners
 *   pointing at a freed pc.Application.
 */
export function installContextLossHandlers(
  canvas: HTMLCanvasElement,
  app: pc.AppBase,
  label: string,
): () => void {
  // ─── Diagnostic instrumentation ─────────────────────────────────────────
  // Production users still report the `Cannot read properties of undefined
  // (reading 'impl')` crash after long inactivity, despite this handler
  // being installed. The hypothesis is a race: the browser releases the
  // context, PlayCanvas's RAF fires one render attempt before the
  // `webglcontextlost` event is dispatched, the render crashes inside
  // `IE.draw` because per-resource `.impl` refs are already nulled, then
  // the event fires and we set `autoRender = false` — but the user has
  // already seen the uncaught error in the console.
  //
  // These logs capture the sequence so we can confirm or refute that
  // hypothesis: install timestamp, visibility state on each transition,
  // event-fire timestamp, the `gl.isContextLost()` flag at handler entry
  // (true ⇒ event fired AFTER PC noticed the loss internally), and a
  // global error listener that catches the 'impl' crash with full
  // context. Strip back to terse warns once the timing is understood.
  const installedAt = Date.now()
  const fmt = (ts: number) => `t+${(ts - installedAt).toLocaleString()}ms`
  console.info(
    `[${label}] context-loss handlers installed`,
    {
      visibility: document.visibilityState,
      hasGl: !!getGl(canvas),
    },
  )

  // Permanent pause acquired on context loss. Never released — page reloads
  // on `webglcontextrestored`. Held in closure so destroy() doesn't have
  // to know about it; if the app teardown happens first, the registry is
  // GC'd with the app.
  let lostToken: RenderPauseToken | null = null
  const onLost = (e: Event): void => {
    e.preventDefault()
    if (!lostToken) lostToken = acquireRenderPause(app, 'webglcontextlost')
    const gl = getGl(canvas)
    console.warn(
      `[${label}] webglcontextlost fired @ ${fmt(Date.now())}`,
      {
        visibility: document.visibilityState,
        glIsContextLost: gl?.isContextLost?.() ?? null,
        statusMessage: (e as WebGLContextEvent).statusMessage || '(none)',
      },
    )
  }
  const onRestored = (): void => {
    console.warn(
      `[${label}] webglcontextrestored fired @ ${fmt(Date.now())} — reloading`,
      { visibility: document.visibilityState },
    )
    window.location.reload()
  }
  const onVisibility = (): void => {
    const gl = getGl(canvas)
    console.info(
      `[${label}] visibilitychange @ ${fmt(Date.now())}`,
      {
        visibility: document.visibilityState,
        glIsContextLost: gl?.isContextLost?.() ?? null,
        autoRender: app.autoRender,
      },
    )
  }
  // Global error listener: catch the uncaught `'impl'` crash so we know
  // whether it fired before or after `webglcontextlost`. Filter strictly
  // to the PlayCanvas signature so we don't spam unrelated errors.
  const onWindowError = (e: ErrorEvent): void => {
    const msg = e.message || e.error?.message || ''
    if (msg.includes("'impl'") || msg.includes('reading \'impl\'')) {
      const gl = getGl(canvas)
      console.error(
        `[${label}] impl-undefined caught by window @ ${fmt(Date.now())}`,
        {
          visibility: document.visibilityState,
          glIsContextLost: gl?.isContextLost?.() ?? null,
          autoRender: app.autoRender,
          msg,
        },
      )
    }
  }

  canvas.addEventListener('webglcontextlost', onLost, false)
  canvas.addEventListener('webglcontextrestored', onRestored, false)
  document.addEventListener('visibilitychange', onVisibility, false)
  window.addEventListener('error', onWindowError, false)
  return () => {
    canvas.removeEventListener('webglcontextlost', onLost, false)
    canvas.removeEventListener('webglcontextrestored', onRestored, false)
    document.removeEventListener('visibilitychange', onVisibility, false)
    window.removeEventListener('error', onWindowError, false)
  }
}

function getGl(canvas: HTMLCanvasElement): WebGL2RenderingContext | WebGLRenderingContext | null {
  // Fetching an existing context with the same type returns the existing one
  // per spec — does NOT create a second context. Safe to call repeatedly.
  return (canvas.getContext('webgl2') as WebGL2RenderingContext | null)
      ?? (canvas.getContext('webgl') as WebGLRenderingContext | null)
}

/**
 * Render-error trap. Wraps `app.tick` in a try/catch that catches the
 * `Cannot read properties of undefined (reading 'impl')` crash family,
 * walks the scene-graph to identify which MeshInstance has stale GPU
 * resources, logs the offender (so we can find the root cause in the
 * codebase), and halts auto-rendering so the spam stops at one frame.
 *
 * Why this exists: production users hit this crash with `glIsContextLost
 * = false`, `autoRender = true`, and `visibility = 'visible'` — i.e.
 * NOT WebGL context loss. The remaining hypothesis is a
 * destroy/rebuild race that leaves a meshInstance pointing at a freed
 * VertexBuffer / Mesh / Material / Shader. Without a trap the renderer
 * crashes again on the next frame and again on the one after — 60 times
 * a second forever — until `installContextLossHandlers`'s window.error
 * listener happens to fire (it doesn't actually halt anything; it just
 * logs).
 *
 * Behaviour:
 *  - On crash: logs the meshInstance entity path, mesh state, material
 *    state, vertex/index buffer state — whatever can be inspected
 *    without re-triggering the same draw call.
 *  - Sets `app.autoRender = false` so subsequent ticks render no-op.
 *  - Re-throws the error so any other `window.error` listeners (e.g.
 *    the diagnostic from `installContextLossHandlers`) still see it
 *    and external monitoring (Sentry, etc.) is not silenced.
 *
 * Recovery: the page goes still rather than freezing in a crash spam.
 * The user can reload to recover. If we get enough diagnostic dumps to
 * pinpoint the destroy-race source, this trap can become a targeted fix
 * and ship as a defensive belt-and-braces on top.
 *
 * @returns cleanup function — restores the original `app.tick`. Call
 *   from the host's destroy() so a fresh app boot starts un-trapped.
 */
export function installRenderErrorTrap(
  app: pc.AppBase, label: string,
): () => void {
  // Capture `app.tick` and rebind to `app` so PlayCanvas internals see
  // the same `this`. We replace the property; tick is called once per
  // RAF by the engine bootstrap.
  const originalTick = (app as unknown as { tick: (dt?: number) => void }).tick.bind(app)
  let tripped = false

  const wrapped = (dt?: number): void => {
    try {
      originalTick(dt)
    } catch (err) {
      const msg = (err as Error)?.message ?? String(err)
      // Filter strictly to the impl-undefined family so unrelated render
      // bugs aren't swallowed.
      if (!msg.includes("'impl'") && !msg.includes('reading \'impl\'')) {
        throw err
      }
      if (!tripped) {
        tripped = true
        // Acquire a render-pause through the registry rather than writing
        // autoRender directly. Otherwise a concurrent rebuild's finally
        // block could `releaseRenderPause` and flip autoRender back to
        // true while the trap thinks render is halted, which restarts
        // the spam.
        acquireRenderPause(app, 'render-trap')
        // Walk the scene to find the offender. Reads are no-ops on a
        // partly-torn-down meshInstance, so the diagnostic itself
        // shouldn't re-trigger the same crash.
        const offenders = findStaleMeshInstances(app)
        // Flat text summary so the console line is readable without
        // expanding the inspector. Entity path + which buffer is bad
        // is what we actually need to locate the destroy-race source.
        const summary = offenders.length === 0
          ? '(no stale mesh-instances found in scene-graph)'
          : offenders.slice(0, 3).map(o => describeOffender(o)).join(' | ')
        console.error(
          `[${label}] render trap: ${offenders.length} stale | ${summary} | autoRender halted`,
          {
            offenderCount: offenders.length,
            offenders: offenders.slice(0, 10),
            originalError: msg,
          },
        )
      }
      throw err
    }
  }

  ;(app as unknown as { tick: (dt?: number) => void }).tick = wrapped
  return (): void => {
    ;(app as unknown as { tick: (dt?: number) => void }).tick = originalTick
  }
}

interface StaleMeshInstanceReport {
  entityPath:    string
  meshOk:        boolean
  vbOk:          boolean
  ibOk:          boolean
  materialOk:    boolean
  shaderOk:      boolean
  instancingOk:  boolean
}

/**
 * Walk every layer's mesh-instance set looking for buffers whose `.impl`
 * field is null/undefined. Returns concise reports so the console log is
 * scannable instead of a 200-entity dump.
 */
function findStaleMeshInstances(app: pc.AppBase): StaleMeshInstanceReport[] {
  const out: StaleMeshInstanceReport[] = []
  const scene = (app as unknown as {
    scene: { layers: { layerList: Array<{ meshInstances: unknown[] }> } }
  }).scene
  const layers = scene?.layers?.layerList ?? []
  for (const layer of layers) {
    for (const mi of layer.meshInstances ?? []) {
      const m = mi as {
        node?: { name?: string; parent?: { name?: string } }
        mesh?: { vertexBuffer?: { impl?: unknown }; indexBuffer?: Array<{ impl?: unknown }> }
        material?: { shader?: { impl?: unknown } }
        instancingData?: { vertexBuffer?: { impl?: unknown } }
      }
      const meshOk        = m.mesh != null
      const vbOk          = m.mesh?.vertexBuffer?.impl != null
      const ibOk          = !m.mesh?.indexBuffer?.length
                              || m.mesh.indexBuffer[0]?.impl != null
      const materialOk    = m.material != null
      const shaderOk      = m.material?.shader == null
                              || m.material.shader.impl != null
      const instancingOk  = m.instancingData?.vertexBuffer == null
                              || m.instancingData.vertexBuffer.impl != null
      if (!(meshOk && vbOk && ibOk && materialOk && shaderOk && instancingOk)) {
        out.push({
          entityPath: pathOf(m.node),
          meshOk, vbOk, ibOk, materialOk, shaderOk, instancingOk,
        })
      }
    }
  }
  return out
}

function pathOf(node: { name?: string; parent?: { name?: string } } | undefined): string {
  if (!node) return '(no-node)'
  const parent = node.parent?.name ?? '?'
  return `${parent}/${node.name ?? '(unnamed)'}`
}

/**
 * Render a stale-mesh-instance report as a one-line scannable string:
 *   "House/Door[mesh!]" — meshOk failed
 *   "Forest/Pine[vb!,instancing!]" — vertexBuffer + instancing buffer freed
 * Only the failing checks appear, so the path stays terse.
 */
function describeOffender(o: StaleMeshInstanceReport): string {
  const fails: string[] = []
  if (!o.meshOk)       fails.push('mesh!')
  if (!o.vbOk)         fails.push('vb!')
  if (!o.ibOk)         fails.push('ib!')
  if (!o.materialOk)   fails.push('material!')
  if (!o.shaderOk)     fails.push('shader!')
  if (!o.instancingOk) fails.push('instancing!')
  return `${o.entityPath}[${fails.join(',')}]`
}

/**
 * Ref-counted render-pause registry attached to a pc.AppBase.
 *
 * Multiple subsystems pause auto-rendering for different reasons —
 * visibility gate ("tab hidden"), rebuild gate ("scene under construction"),
 * context-loss gate ("WebGL context lost"). Each used to write
 * `app.autoRender` directly, which created a composition race: the gate
 * with the most-recent write wins, even if other gates still want render
 * paused. Production crash signature: visibility-gate fires "tab visible
 * → autoRender = true" while rebuild is mid-async-build, partial scene
 * graph renders against a half-torn-down state, `IE.draw` crashes on
 * undefined `.impl`.
 *
 * Each gate `acquire()`s a token; render is paused while ANY token is
 * outstanding. `release()` decrements; when the last token is released,
 * `autoRender` returns to `true`. Idempotent — calling `release()` on a
 * stale token is a no-op.
 */
type RenderPauseToken = { released: boolean }
interface RenderPauseRegistry {
  acquire(reason: string): RenderPauseToken
  release(token: RenderPauseToken): void
}

interface AppWithPauseRegistry {
  __renderPause?: RenderPauseRegistry
}

function getRenderPauseRegistry(app: pc.AppBase): RenderPauseRegistry {
  const slot = app as unknown as AppWithPauseRegistry
  if (slot.__renderPause) return slot.__renderPause
  let activeCount = 0
  const reg: RenderPauseRegistry = {
    acquire(_reason: string): RenderPauseToken {
      activeCount++
      app.autoRender = false
      return { released: false }
    },
    release(token: RenderPauseToken): void {
      if (token.released) return
      token.released = true
      activeCount--
      if (activeCount <= 0) {
        activeCount = 0
        app.autoRender = true
      }
    },
  }
  slot.__renderPause = reg
  return reg
}

/**
 * Acquire a render-pause token from this app's registry. Render stays
 * paused until `release()` is called on the returned token. Use this
 * in any subsystem that needs auto-rendering off for a window — never
 * write `app.autoRender = false` directly, or you'll race with peers.
 */
export function acquireRenderPause(
  app: pc.AppBase, reason: string,
): RenderPauseToken {
  return getRenderPauseRegistry(app).acquire(reason)
}

export function releaseRenderPause(
  app: pc.AppBase, token: RenderPauseToken,
): void {
  getRenderPauseRegistry(app).release(token)
}

/**
 * Pause auto-rendering while the document is hidden (background tab,
 * minimized window). Resumes when visible.
 *
 * Uses the ref-counted render-pause registry rather than writing
 * `autoRender` directly so it composes safely with the rebuild gate
 * and any future gates. The previous direct-write implementation
 * raced with `SceneManager.rebuild` and was the suspected root cause
 * of the recurring `'impl'` undefined crash that was NOT context loss.
 *
 * @returns cleanup function — detaches the visibilitychange listener.
 */
export function installVisibilityGate(app: pc.AppBase): () => void {
  let token: RenderPauseToken | null = null
  const onChange = (): void => {
    if (document.hidden) {
      if (!token) token = acquireRenderPause(app, 'visibility:hidden')
    } else if (token) {
      releaseRenderPause(app, token)
      token = null
    }
  }
  // Initial state — if we mount with a hidden tab (rare, e.g. background
  // window-restore), pause immediately.
  if (document.hidden) {
    token = acquireRenderPause(app, 'visibility:hidden')
  }
  document.addEventListener('visibilitychange', onChange, false)
  return () => {
    document.removeEventListener('visibilitychange', onChange, false)
    if (token) {
      releaseRenderPause(app, token)
      token = null
    }
  }
}
