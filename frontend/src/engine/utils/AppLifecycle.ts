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

  const onLost = (e: Event): void => {
    e.preventDefault()
    app.autoRender = false
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
 * Pause `app.autoRender` while the document is hidden (background tab,
 * minimized window). Restores rendering when the tab becomes visible.
 *
 * Two production wins from this gate:
 *   1. CPU + GPU savings while the user has the tab in the background
 *      — RAF still fires throttled but every frame is now a no-op.
 *   2. Reduces the GPU memory pressure that prompts the browser to
 *      reclaim the WebGL context in the first place — i.e. it is
 *      *prevention* for the context-loss class of bug, complementing
 *      `installContextLossHandlers` which only handles the aftermath.
 *
 * Composition caveat: this gate writes `app.autoRender` directly. If a
 * code path elsewhere (e.g. `SceneManager.rebuild`'s try/finally render
 * pause) is also flipping the same flag, the two writes can race within
 * a narrow window. Acceptable today because the rebuild gate self-heals
 * on its `finally` and visibility transitions are user-initiated. If a
 * third gate appears, lift to ref-counted gates owned by the host.
 *
 * @returns cleanup function — detaches the visibilitychange listener.
 */
export function installVisibilityGate(app: pc.AppBase): () => void {
  const onChange = (): void => {
    app.autoRender = !document.hidden
  }
  document.addEventListener('visibilitychange', onChange, false)
  return () => {
    document.removeEventListener('visibilitychange', onChange, false)
  }
}
