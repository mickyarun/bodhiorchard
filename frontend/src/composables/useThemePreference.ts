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

// Theme preference with three modes, persisted to localStorage:
//   * 'system' (default) — follow the OS colour-scheme and live-update when
//     it changes (e.g. macOS auto light→dark at sunset).
//   * 'light' / 'dark'   — an explicit override the user picked.
// Both Vuetify themes (and the matching tokens.css overrides) already exist;
// this just decides which is active and remembers the user's choice.

import { computed, onScopeDispose, ref } from 'vue'
import { useTheme } from 'vuetify'

export const THEME_DARK = 'bodhiorchardDark'
export const THEME_LIGHT = 'bodhiorchardLight'

export type ThemePreference = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'bodhiorchard_theme'
const SYSTEM_LIGHT_QUERY = '(prefers-color-scheme: light)'

function readStoredPreference(): ThemePreference {
  if (typeof window === 'undefined') return 'system'
  const v = window.localStorage.getItem(STORAGE_KEY)
  return v === 'light' || v === 'dark' || v === 'system' ? v : 'system'
}

/** The Vuetify theme name the OS is currently asking for. */
function systemThemeName(): string {
  if (typeof window === 'undefined' || !window.matchMedia) return THEME_DARK
  return window.matchMedia(SYSTEM_LIGHT_QUERY).matches ? THEME_LIGHT : THEME_DARK
}

/** A preference resolved to the concrete Vuetify theme name. */
function preferenceToThemeName(pref: ThemePreference): string {
  if (pref === 'light') return THEME_LIGHT
  if (pref === 'dark') return THEME_DARK
  return systemThemeName()
}

/**
 * Resolve the theme to apply at startup, read synchronously so Vuetify can
 * render the correct theme on the first paint (no flash). SSR-safe: returns
 * dark when there is no `window` (e.g. the SSG landing build).
 */
export function resolveInitialThemeName(): string {
  return preferenceToThemeName(readStoredPreference())
}

/**
 * Reactive theme control. `preference` is the user's choice (system / light /
 * dark); setting it persists and applies. While the preference is 'system'
 * the active theme tracks the OS colour-scheme live.
 */
export function useThemePreference() {
  const theme = useTheme()

  const preference = ref<ThemePreference>(readStoredPreference())
  const isDark = computed(() => theme.global.name.value === THEME_DARK)

  function setPreference(pref: ThemePreference): void {
    preference.value = pref
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(STORAGE_KEY, pref)
    }
    theme.global.name.value = preferenceToThemeName(pref)
  }

  // Live-follow the OS while the preference is 'system'.
  if (typeof window !== 'undefined' && window.matchMedia) {
    const mq = window.matchMedia(SYSTEM_LIGHT_QUERY)
    const onSystemChange = (): void => {
      if (preference.value === 'system') {
        theme.global.name.value = systemThemeName()
      }
    }
    mq.addEventListener?.('change', onSystemChange)
    onScopeDispose(() => mq.removeEventListener?.('change', onSystemChange))
  }

  return { preference, isDark, setPreference }
}
