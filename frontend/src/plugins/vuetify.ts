import 'vuetify/styles'
import { createVuetify, type ThemeDefinition } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'

const bodhigroveDark: ThemeDefinition = {
  dark: true,
  colors: {
    background: '#0f1117',
    surface: '#1a1d2e',
    'surface-variant': '#242738',
    primary: '#2563EB',
    secondary: '#7C3AED',
    error: '#ef4444',
    success: '#22c55e',
    warning: '#f59e0b',
    info: '#3b82f6',
    'on-background': '#e2e8f0',
    'on-surface': '#e2e8f0',
    'on-primary': '#ffffff',
    'on-secondary': '#ffffff',
  },
}

const bodhigroveLight: ThemeDefinition = {
  dark: false,
  colors: {
    background: '#f8fafc',
    surface: '#ffffff',
    'surface-variant': '#f1f5f9',
    primary: '#2563EB',
    secondary: '#7C3AED',
    error: '#ef4444',
    success: '#22c55e',
    warning: '#f59e0b',
    info: '#3b82f6',
    'on-background': '#0f172a',
    'on-surface': '#0f172a',
    'on-primary': '#ffffff',
    'on-secondary': '#ffffff',
  },
}

export default createVuetify({
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
  theme: {
    defaultTheme: 'bodhigroveDark',
    themes: {
      bodhigroveDark,
      bodhigroveLight,
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
  },
})
