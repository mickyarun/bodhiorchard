// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

import { ViteSSG } from 'vite-ssg/single-page'
import LandingApp from './LandingApp.vue'
import vuetify from '@/plugins/vuetify'
import '@mdi/font/css/materialdesignicons.css'
import '@/assets/styles/main.scss'

export const createApp = ViteSSG(LandingApp, ({ app }) => {
  app.use(vuetify)
})
