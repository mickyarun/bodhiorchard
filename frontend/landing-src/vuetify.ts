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

// Landing-only Vuetify instance. The marketing site is pre-rendered (vite-ssg)
// and always dark, so it hard-codes `bodhiorchardDark` and never calls
// resolveInitialThemeName() — reading localStorage during SSR would crash the
// build and mismatch hydration. Theme + defaults are the shared Hallmark set.

import 'vuetify/styles'
import { createVuetify } from 'vuetify'
import { aliases, mdi } from 'vuetify/iconsets/mdi'
import { bodhiorchardThemes, vuetifyDefaults } from '@/plugins/vuetify-theme'

export default createVuetify({
  icons: {
    defaultSet: 'mdi',
    aliases,
    sets: { mdi },
  },
  theme: {
    defaultTheme: 'bodhiorchardDark',
    themes: bodhiorchardThemes,
  },
  defaults: vuetifyDefaults,
})
