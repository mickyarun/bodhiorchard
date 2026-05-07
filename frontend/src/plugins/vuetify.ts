// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import 'vuetify/styles'
import { createVuetify, type ThemeDefinition } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'

const bodhiorchardDark: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0D1B0F',
    surface: '#152415',
    'surface-variant': '#1E3220',
    primary: '#2E7D32',
    secondary: '#D4A843',
    error: '#EF5350',
    success: '#66BB6A',
    warning: '#F9A825',
    info: '#3b82f6',
    'on-background': '#E8F5E9',
    'on-surface': '#E8F5E9',
    // Muted text on the dark green surface. Vuetify's default
    // ``on-surface-variant`` is near-black, which renders metadata
    // (repo names, hints, "Optional" labels) invisibly against our
    // surface. A desaturated sage keeps it readable but quieter than
    // the primary on-surface tone.
    'on-surface-variant': '#A5D6A7',
    'on-primary': '#ffffff',
    'on-secondary': '#1a1a1a',
  },
}

const bodhiorchardLight: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#F1F8E9',
    surface: '#ffffff',
    'surface-variant': '#E8F5E9',
    primary: '#2E7D32',
    secondary: '#D4A843',
    error: '#EF5350',
    success: '#66BB6A',
    warning: '#F9A825',
    info: '#3b82f6',
    'on-background': '#1B2E1C',
    'on-surface': '#1B2E1C',
    'on-primary': '#ffffff',
    'on-secondary': '#1a1a1a',
  },
}

export default createVuetify({
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
  theme: {
    defaultTheme: 'bodhiorchardDark',
    themes: {
      bodhiorchardDark,
      bodhiorchardLight,
    },
  },
  defaults: {
    VCard: {
      rounded: 'lg',
      elevation: 0,
    },
    VBtn: {
      rounded: 'lg',
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
    VSwitch: {
      color: 'primary',
      inset: true,
    },
    VTooltip: {
      contentClass: 'bg-grey-darken-4 text-white',
    },
  },
})
