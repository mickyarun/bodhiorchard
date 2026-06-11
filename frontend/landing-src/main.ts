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

// Landing-site entry. vite-ssg's router build pre-renders every route in
// router.ts to its own HTML file. LandingLayout is the shell (nav + footer +
// <router-view>); per-route <head> is set by useSeo() inside each page via
// unhead (bundled by vite-ssg). Uses the landing-only dark Vuetify instance.

import { ViteSSG } from 'vite-ssg'
import LandingLayout from './LandingLayout.vue'
import { routes } from './router'
import vuetify from './vuetify'
import '@mdi/font/css/materialdesignicons.css'
import '@/assets/styles/tokens.css'
import '@/assets/styles/main.scss'

export const createApp = ViteSSG(
  LandingLayout,
  {
    routes,
    scrollBehavior: () => ({ top: 0 }),
  },
  ({ app }) => {
    app.use(vuetify)
  },
)
