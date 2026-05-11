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

import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', component: () => import('./views/auth/LoginView.vue') },
    { path: '/register', component: () => import('./views/auth/RegisterView.vue') },
    { path: '/tasks', component: () => import('./views/tasks/TaskBoard.vue') },
    { path: '/tasks/:id', component: () => import('./views/tasks/TaskDetail.vue') },
    { path: '/billing', component: () => import('./views/billing/PlansView.vue') },
  ],
})

const app = createApp(App)
app.use(router)
app.mount('#app')
