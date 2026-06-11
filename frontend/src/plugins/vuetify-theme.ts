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

// Hallmark design system — Bodhiorchard. Shared Vuetify theme definitions and
// component defaults, with NO runtime/browser dependency (no localStorage), so
// they can be reused by both the main app plugin and the SSR-prerendered
// landing site. The hex values are the sRGB equivalents of the OKLCH tokens in
// assets/styles/tokens.css (the source of record) — keep the two in sync.

import type { ThemeDefinition } from 'vuetify'

export const bodhiorchardDark: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#07130A', // paper   — deep forest canvas
    surface: '#0F1C12', // paper-2 — card surface (+1)
    'surface-bright': '#18251B', // paper-3 — elevated / hover (+2)
    'surface-light': '#18251B',
    'surface-variant': '#18251B',
    primary: '#3EAB5E', // leaf-green — the one brand accent
    secondary: '#E4B750', // harvest gold — reward / XP signal only
    error: '#E45D53',
    success: '#61C568',
    warning: '#F1AA57',
    info: '#45AADE',
    'on-background': '#E6EEE7', // ink   (sage-white)
    'on-surface': '#E6EEE7',
    // Muted metadata text. Vuetify's default ``on-surface-variant`` is
    // near-black and disappears on our dark surface; this sage keeps
    // hints / repo names / "Optional" labels readable but quiet.
    'on-surface-variant': '#808982', // muted
    'on-primary': '#071009', // accent-ink — dark text on the green fill
    'on-secondary': '#211909', // gold-ink
    // Extra system tokens, exposed as Vuetify colours so components can use
    // ``color="gold"`` / ``text-ink-2`` / ``border`` against ``rule``.
    gold: '#E4B750',
    'on-gold': '#211909',
    'ink-2': '#B1BAB3',
    muted: '#808982',
    rule: '#2A332C',
  },
  variables: {
    'border-color': '#E6EEE7',
    'border-opacity': 0.09,
    'high-emphasis-opacity': 0.95,
    'medium-emphasis-opacity': 0.68,
  },
}

export const bodhiorchardLight: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#E4F1E6', // paper — deeper sage so white cards clearly float
    surface: '#FBFEFB', // paper-2 (whiter card)
    'surface-bright': '#FFFFFF',
    'surface-light': '#DAE7DC', // paper-3
    'surface-variant': '#DAE7DC',
    primary: '#007834', // deep leaf-green
    secondary: '#C28E24', // harvest gold
    error: '#C53732',
    success: '#1B7E2A',
    warning: '#D78C29',
    info: '#007BB2',
    'on-background': '#141D16', // ink
    'on-surface': '#141D16',
    'on-surface-variant': '#69716A', // muted
    'on-primary': '#F4FAF5',
    'on-secondary': '#211909',
    gold: '#C28E24',
    'on-gold': '#211909',
    'ink-2': '#414B43',
    muted: '#69716A',
    rule: '#B4C2B6',
  },
  variables: {
    'border-color': '#141D16',
    'border-opacity': 0.16,
    'high-emphasis-opacity': 0.95,
    'medium-emphasis-opacity': 0.66,
  },
}

export const bodhiorchardThemes = {
  bodhiorchardDark,
  bodhiorchardLight,
}

// Flat, bordered surfaces — the design system carries depth through
// elevation-as-lightness (paper → paper-2 → paper-3), not drop shadows.
export const vuetifyDefaults = {
  VCard: {
    rounded: 'lg',
    elevation: 0,
  },
  VBtn: {
    rounded: 'lg',
    // Roman, not uppercase; weight carries emphasis (Hallmark typography).
    class: 'text-none font-weight-medium',
  },
  VTextField: {
    variant: 'outlined',
    density: 'comfortable',
    color: 'primary',
  },
  VSelect: {
    variant: 'outlined',
    density: 'comfortable',
    color: 'primary',
  },
  VTextarea: {
    variant: 'outlined',
    color: 'primary',
  },
  VSwitch: {
    color: 'primary',
    inset: true,
  },
  VCheckbox: {
    color: 'primary',
  },
  VChip: {
    rounded: 'md',
  },
  VTooltip: {
    // Token-driven tooltip (styled in main.scss) — replaces the hard-coded
    // grey-darken-4 so tooltips track the active theme.
    contentClass: 'bo-tooltip',
  },
}
