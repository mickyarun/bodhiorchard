// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Resolve the Colyseus endpoint URL.
 *
 * Precedence:
 *   1. `VITE_COLYSEUS_URL` build-time env var — prod deploys where
 *      Colyseus lives at a known hostname.
 *   2. **Page-origin proxy path** — `ws(s)://<current-host>/colyseus`,
 *      which Vite's dev proxy forwards to `ws://localhost:2567`. This
 *      works transparently for:
 *        * MacBook local dev (`http://localhost:3000` → ws through proxy),
 *        * ngrok HTTPS tunnels (`https://*.ngrok.app` → wss through proxy
 *          — no mixed-content block because the WS is same-origin),
 *        * Tailscale Serve / any other reverse proxy sitting on port 80.
 *   3. `ws://localhost:2567` fallback for non-browser contexts (tests).
 *
 * Why not hit `localhost:2567` directly? Browsers block HTTP/WS
 * requests from HTTPS pages (mixed-content policy). When you load
 * the app through ngrok/Tailscale HTTPS, Colyseus MUST be reached
 * via the same HTTPS origin or the connection is refused before it
 * even opens.
 */

export function resolveColyseusUrl(): string {
  const envUrl = import.meta.env.VITE_COLYSEUS_URL
  if (typeof envUrl === 'string' && envUrl.length > 0) return envUrl

  if (typeof window !== 'undefined' && window.location?.host) {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}/colyseus`
  }

  return 'ws://localhost:2567'
}
