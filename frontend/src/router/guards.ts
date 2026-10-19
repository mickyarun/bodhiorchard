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
 * Global navigation guards: setup wizard, sign-in, workspace and
 * permission checks, plus the top progress bar.
 *
 * The backend is the real gate on every route; these guards only keep
 * people from landing on a page whose API calls would all 403. When a
 * redirect is needed it goes to the user's own home (``homeRouteFor``)
 * rather than a fixed page, so a sales user is never bounced to the
 * engineering dashboard and back.
 */
import {
  isNavigationFailure,
  NavigationFailureType,
  type RouteLocationNormalized,
  type RouteLocationRaw,
  type Router,
} from 'vue-router'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { useNavigationProgress } from '@/composables/useNavigationProgress'
import { canOpenWorkspace, homeRouteFor } from '@/utils/workspace'
import './routeMeta'

const TOKEN_KEY = 'bodhiorchard_token'
const SETUP_KEY = 'bodhiorchard_setup_complete'

/** Public routes that don't require authentication. */
const PUBLIC_ROUTES = new Set(['setup', 'login', 'methodology', 'tree-demo', 'house-demo'])

let setupChecked = false
let isSetupComplete = false

/** Call after setup completes so the next navigation re-checks the backend. */
export function resetSetupCache(): void {
  setupChecked = false
  isSetupComplete = false
}

async function checkSetupStatus(): Promise<boolean> {
  // Return cached result for subsequent in-session navigations
  if (setupChecked) return isSetupComplete

  // Always verify against backend on first navigation
  try {
    const { data } = await api.get('/setup/status')
    isSetupComplete = data.is_setup_complete === true
    // Sync localStorage with backend truth
    if (isSetupComplete) {
      localStorage.setItem(SETUP_KEY, 'true')
    } else {
      localStorage.removeItem(SETUP_KEY)
    }
  } catch {
    // Backend unreachable — fall back to localStorage as last resort
    isSetupComplete = localStorage.getItem(SETUP_KEY) === 'true'
  }

  setupChecked = true
  return isSetupComplete
}

/**
 * The signed-in user's permissions, loading the profile on first use.
 * ``null`` when it can't be loaded (network blip): callers then skip
 * client-side redirects instead of guessing and sending an engineer to
 * the people workspace.
 */
async function loadPermissions(): Promise<string[] | null> {
  const authStore = useAuthStore()
  if (!authStore.user && localStorage.getItem(TOKEN_KEY)) {
    try {
      await authStore.fetchUser()
    } catch {
      return null
    }
  }
  return authStore.user?.permissions ?? null
}

function satisfies(permissions: string[], required: string | string[]): boolean {
  return Array.isArray(required)
    ? required.some(p => permissions.includes(p))
    : permissions.includes(required)
}

async function accessRedirect(to: RouteLocationNormalized): Promise<RouteLocationRaw | null> {
  const { workspace, permission } = to.meta
  if (!workspace && !permission) return null
  const permissions = await loadPermissions()
  if (permissions === null) return null
  if (workspace && !canOpenWorkspace(permissions, workspace)) return homeRouteFor(permissions)
  if (permission && !satisfies(permissions, permission)) return homeRouteFor(permissions)
  return null
}

export function installGuards(router: Router): void {
  const navProgress = useNavigationProgress()

  router.beforeEach(async (to) => {
    // Light the top progress bar the instant a navigation begins — this is
    // the only feedback that covers the lazy-chunk download for heavy views
    // like BUDDetail, whose own spinner can't render until it has mounted.
    navProgress.start()

    const done = await checkSetupStatus()
    const hasToken = !!localStorage.getItem(TOKEN_KEY)

    // Setup not done — force to setup wizard
    if (!done && to.name !== 'setup') {
      return { name: 'setup' }
    }

    // Auth guard — require token for protected routes
    if (done && !PUBLIC_ROUTES.has(to.name as string) && !hasToken) {
      return { name: 'login' }
    }

    // Setup done, or already signed in — leave setup/login for home
    if ((done && to.name === 'setup') || (to.name === 'login' && hasToken)) {
      return homeRouteFor(await loadPermissions())
    }

    return (await accessRedirect(to)) ?? true
  })

  // A ``cancelled`` failure means a newer navigation superseded this one —
  // e.g. the user clicked a second BUD before the first resolved (the exact
  // "keep clicking" behaviour this bar exists to soothe). That successor has
  // already lit the bar and owns turning it off, so clearing here would flash
  // it off mid-flight. Every other outcome is terminal and should clear:
  // a successful landing, an abort (guard returned ``false``), or a duplicate.
  // Redirects don't reach here as a distinct event — vue-router resolves the
  // redirect chain before firing ``afterEach`` once, for the final landing.
  router.afterEach((_to, _from, failure) => {
    if (isNavigationFailure(failure, NavigationFailureType.cancelled)) return
    navProgress.stop()
  })
  // ``afterEach`` is skipped when a guard throws or an async-component (chunk)
  // load rejects — vue-router routes those through ``onError`` instead. This
  // is the safety net that prevents the bar sticking on after a failed load.
  router.onError(() => {
    navProgress.stop()
  })
}
