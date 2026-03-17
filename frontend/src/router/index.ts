import { createRouter, createWebHistory } from 'vue-router'
import api from '@/services/api'

let setupChecked = false
let isSetupComplete = false

async function checkSetupStatus(): Promise<boolean> {
  // Return cached result for subsequent in-session navigations
  if (setupChecked) return isSetupComplete

  // Always verify against backend on first navigation
  try {
    const { data } = await api.get('/setup/status')
    isSetupComplete = data.is_setup_complete === true
    // Sync localStorage with backend truth
    if (isSetupComplete) {
      localStorage.setItem('flowdev_setup_complete', 'true')
    } else {
      localStorage.removeItem('flowdev_setup_complete')
    }
  } catch {
    // Backend unreachable — fall back to localStorage as last resort
    isSetupComplete = localStorage.getItem('flowdev_setup_complete') === 'true'
  }

  setupChecked = true
  return isSetupComplete
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/dashboard',
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
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('@/views/DashboardPlaceholder.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const done = await checkSetupStatus()

  if (!done && to.name !== 'setup') {
    return { name: 'setup' }
  }

  if (done && to.name === 'setup') {
    return { name: 'dashboard' }
  }
})

export default router
