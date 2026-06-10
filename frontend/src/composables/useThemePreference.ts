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

// Light/dark theme preference: persisted to localStorage, defaulting to the
// OS colour-scheme on first visit. Both Vuetify themes (and the matching
// CSS-custom-property overrides in tokens.css) already exist; this just
// drives which one is active and remembers the user's choice.

import { computed } from 'vue'
import { useTheme } from 'vuetify'

export const THEME_DARK = 'bodhiorchardDark'
export const THEME_LIGHT = 'bodhiorchardLight'

const STORAGE_KEY = 'bodhiorchard_theme'

/**
 * Resolve the theme to apply at startup, read synchronously so Vuetify can
 * render the correct theme on the first paint (no flash of the wrong theme).
 * Order: saved preference → OS `prefers-color-scheme` → dark.
 * SSR-safe: returns dark when there is no `window` (e.g. the SSG landing build).
 */
export function resolveInitialThemeName(): string {
  if (typeof window === 'undefined') return THEME_DARK
  const saved = window.localStorage.getItem(STORAGE_KEY)
  if (saved === THEME_DARK || saved === THEME_LIGHT) return saved
  const prefersLight = window.matchMedia?.('(prefers-color-scheme: light)').matches
  return prefersLight ? THEME_LIGHT : THEME_DARK
}

/**
 * Reactive light/dark control for use in components. Flipping the toggle
 * updates Vuetify's active theme and persists the choice.
 */
export function useThemePreference() {
  const theme = useTheme()

  const isDark = computed(() => theme.global.name.value === THEME_DARK)

  function setDark(dark: boolean): void {
    const name = dark ? THEME_DARK : THEME_LIGHT
    theme.global.name.value = name
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, name)
    }
  }

  function toggle(): void {
    setDark(!isDark.value)
  }

  return { isDark, toggle, setDark }
}
