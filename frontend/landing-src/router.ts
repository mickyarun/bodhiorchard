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

// Route table for the landing site. vite-ssg builds the router instance from
// this array and crawls every static path, pre-rendering each to its own HTML.
// Page components are lazy-imported; the catch-all is excluded from the SSG
// crawl in vite.landing.config.ts (it can't be statically enumerated).

import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: () => import('./pages/HomePage.vue') },
  { path: '/methodology', name: 'methodology', component: () => import('./pages/MethodologyPage.vue') },
  { path: '/agents', name: 'agents', component: () => import('./pages/AgentsPage.vue') },
  { path: '/platform', name: 'platform', component: () => import('./pages/PlatformPage.vue') },
  { path: '/vs-agile', name: 'vs-agile', component: () => import('./pages/VsAgilePage.vue') },
  { path: '/why-bodhiorchard', name: 'why', component: () => import('./pages/WhyBodhiorchardPage.vue') },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./pages/NotFoundPage.vue') },
]
