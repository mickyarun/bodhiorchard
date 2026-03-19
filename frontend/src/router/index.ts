import { createRouter, createWebHistory } from 'vue-router'
import api from '@/services/api'

let setupChecked = false
let isSetupComplete = false

/** Call after setup completes so the next navigation re-checks the backend. */
export function resetSetupCache(): void {
  setupChecked = false
  isSetupComplete = false
}

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

/** Public routes that don't require authentication. */
const PUBLIC_ROUTES = new Set(['setup', 'login'])

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
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
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/DashboardPlaceholder.vue'),
        },
        {
          path: 'prds',
          name: 'prds',
          component: () => import('@/views/prds/PRDBoard.vue'),
        },
        {
          path: 'prds/:id',
          name: 'prd-detail',
          component: () => import('@/views/prds/PRDDetail.vue'),
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/settings/SettingsConnections.vue'),
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const done = await checkSetupStatus()

  // Setup not done — force to setup wizard
  if (!done && to.name !== 'setup') {
    return { name: 'setup' }
  }

  // Setup done — don't allow going back to setup
  if (done && to.name === 'setup') {
    return { name: 'dashboard' }
  }

  // Auth guard — require token for protected routes
  if (done && !PUBLIC_ROUTES.has(to.name as string)) {
    const hasToken = !!localStorage.getItem('flowdev_token')
    if (!hasToken) {
      return { name: 'login' }
    }
  }

  // Already logged in — redirect away from login
  if (to.name === 'login' && localStorage.getItem('flowdev_token')) {
    return { name: 'dashboard' }
  }
})

export default router
