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
  const onLost = (e: Event): void => {
    e.preventDefault()
    app.autoRender = false
    console.warn(
      `[${label}] WebGL context lost — rendering halted. Waiting for restore.`,
    )
  }
  const onRestored = (): void => {
    console.warn(
      `[${label}] WebGL context restored — reloading page to rebuild GPU resources.`,
    )
    window.location.reload()
  }
  canvas.addEventListener('webglcontextlost', onLost, false)
  canvas.addEventListener('webglcontextrestored', onRestored, false)
  return () => {
    canvas.removeEventListener('webglcontextlost', onLost, false)
    canvas.removeEventListener('webglcontextrestored', onRestored, false)
  }
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
