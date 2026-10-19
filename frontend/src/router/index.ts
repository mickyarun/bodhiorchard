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

import { createRouter, createWebHistory } from 'vue-router'
import { installGuards } from './guards'
import { engineeringRoutes } from './routes/engineering'
import { peopleRoutes } from './routes/people'

export { resetSetupCache } from './guards'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      // People-only roles are sent on from the dashboard to their own
      // home by the workspace guard, so one fixed redirect serves everyone.
      path: '/',
      redirect: '/dashboard',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/setup',
      component: () => import('@/layouts/SetupLayout.vue'),
      children: [
        {
          path: '',
          name: 'setup',
          component: () => import('@/views/setup/SetupWizard.vue'),
        },
      ],
    },
    {
      path: '/change-password',
      name: 'change-password',
      component: () => import('@/views/ChangePasswordView.vue'),
    },
    {
      path: '/methodology',
      name: 'methodology',
      component: () => import('@/views/methodology/MethodologyView.vue'),
    },
    {
      // The garden avatar picker — part of the engineering workspace.
      path: '/character-select',
      name: 'character-select',
      meta: { workspace: 'engineering' },
      component: () => import('@/views/character/CharacterSelectView.vue'),
    },
    {
      path: '/tree-demo',
      name: 'tree-demo',
      component: () => import('@/views/test/TreeTestView.vue'),
    },
    {
      path: '/house-demo',
      name: 'house-demo',
      component: () => import('@/views/test/HouseTestView.vue'),
    },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [...engineeringRoutes, ...peopleRoutes],
    },
  ],
})

installGuards(router)

export default router
