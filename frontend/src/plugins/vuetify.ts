import 'vuetify/styles'
import { createVuetify, type ThemeDefinition } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'

const bodhigroveDark: ThemeDefinition = {
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
    'on-primary': '#ffffff',
    'on-secondary': '#1a1a1a',
  },
}

const bodhigroveLight: ThemeDefinition = {
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
