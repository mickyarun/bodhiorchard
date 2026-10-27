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

// Design system — Glideship. Shared Vuetify theme definitions and component
// defaults, with NO runtime/browser dependency (no localStorage), so they can
// be reused by both the main app plugin and the SSR-prerendered landing site.
// The hex values mirror assets/styles/tokens.css (the source of record) —
// keep the two in sync.

import type { ThemeDefinition } from 'vuetify'

export const glideshipDark: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0B1120', // paper   — app canvas
    surface: '#111827', // paper-2 — card surface (+1)
    'surface-bright': '#1A2233', // paper-3 — elevated / hover (+2)
    'surface-light': '#1A2233',
    'surface-variant': '#1A2233',
    // Dark-tone action blue: a light fill with dark ink keeps both button
    // labels (7.4:1) and blue text on cards (7.0:1) above AA.
    primary: '#60A5FA',
    secondary: '#E4B750', // gold — reward / XP signal only
    error: '#F87171',
    success: '#4ADE80',
    warning: '#FBBF24',
    info: '#38BDF8',
    'on-background': '#E5E9F0', // ink
    'on-surface': '#E5E9F0',
    // Muted metadata text. Vuetify's default ``on-surface-variant`` is
    // near-black and disappears on our dark surface; this slate keeps
    // hints / repo names / "Optional" labels readable but quiet.
    'on-surface-variant': '#94A3B8', // muted
    'on-primary': '#0B1120', // accent-ink — dark text on the blue fill
    'on-secondary': '#211909', // gold-ink
    // Extra system tokens, exposed as Vuetify colours so components can use
    // ``color="gold"`` / ``text-ink-2`` / ``border`` against ``rule``.
    gold: '#E4B750',
    'on-gold': '#211909',
    brand: '#818CF8', // indigo — brand accent, never an action colour
    'ink-2': '#CBD2DC',
    muted: '#94A3B8',
    rule: '#222C3D',
  },
  variables: {
    'border-color': '#E5E9F0',
    'border-opacity': 0.09,
    'high-emphasis-opacity': 0.95,
    'medium-emphasis-opacity': 0.68,
  },
}

export const glideshipLight: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#F7F8FA', // paper — cool off-white so white cards float
    surface: '#FFFFFF', // paper-2
    // Hover / raised fills — paper-3, mirroring dark. White here would be
    // identical to `surface` and make every hover state invisible.
    'surface-bright': '#F1F3F6', // paper-3
    'surface-light': '#F1F3F6',
    'surface-variant': '#F1F3F6',
    primary: '#2563EB', // action blue — 5.2:1 on white
    secondary: '#C28E24', // gold — reward / XP signal only
    error: '#DC2626',
    success: '#15803D',
    warning: '#B45309',
    info: '#0369A1',
    'on-background': '#0F172A', // ink
    'on-surface': '#0F172A',
    'on-surface-variant': '#5B6474', // muted
    'on-primary': '#FFFFFF',
    'on-secondary': '#211909',
    gold: '#C28E24',
    'on-gold': '#211909',
    brand: '#3730A3', // indigo — brand accent, never an action colour
    'ink-2': '#334155',
    muted: '#5B6474',
    rule: '#E3E6EB',
  },
  variables: {
    'border-color': '#0F172A',
    'border-opacity': 0.12,
    'high-emphasis-opacity': 0.95,
    'medium-emphasis-opacity': 0.66,
  },
}

export const glideshipThemes = {
  glideshipDark,
  glideshipLight,
}

// Flat, bordered surfaces — depth comes from elevation-as-lightness
// (paper → paper-2 → paper-3), not drop shadows.
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
