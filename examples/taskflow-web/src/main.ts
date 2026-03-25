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
