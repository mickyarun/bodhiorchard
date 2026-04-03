<template>
  <v-app>
    <!-- Sidebar -->
    <v-navigation-drawer permanent color="surface" width="240" class="app-sidebar">
      <div class="pa-4 pb-2 d-flex align-center justify-space-between">
        <BodhigroveLogo :size="28" />
        <NotificationBell v-if="authStore.user?.id" :user-id="authStore.user.id" />
      </div>

      <v-list density="compact" nav class="px-2">
        <v-list-item
          prepend-icon="mdi-view-dashboard-outline"
          title="Dashboard"
          to="/dashboard"
          rounded="lg"
        />
        <v-list-item
          prepend-icon="mdi-seed-outline"
          title="BUDs"
          to="/buds"
          rounded="lg"
        />
        <v-list-item
          prepend-icon="mdi-lightbulb-outline"
          title="Features"
          to="/features"
          rounded="lg"
        />
        <v-list-item
          prepend-icon="mdi-bug-outline"
          title="Bugs"
          rounded="lg"
          disabled
        />
        <v-list-item
          prepend-icon="mdi-trophy-outline"
          title="Leaderboard"
          to="/leaderboard"
          rounded="lg"
        />
        <v-list-item
          prepend-icon="mdi-account-cog-outline"
          title="Skills"
          to="/skills"
          rounded="lg"
        />
        <v-list-item
          v-if="canApprove"
          prepend-icon="mdi-clipboard-check-outline"
          title="Approvals"
          to="/triage"
          rounded="lg"
        />
        <v-list-item
          v-if="canManageMembers"
          prepend-icon="mdi-account-group-outline"
          title="Members"
          to="/members"
          rounded="lg"
        />
      </v-list>

      <template #append>
        <v-divider class="mb-2" />
        <v-list density="compact" nav class="px-2 pb-2">
          <v-list-group v-if="canViewSettings" value="settings">
            <template #activator="{ props }">
              <v-list-item
                v-bind="props"
                prepend-icon="mdi-cog-outline"
                title="Settings"
                rounded="lg"
              />
            </template>
            <v-list-item
              v-if="canViewConnections"
              title="Integrations"
              to="/settings"
              rounded="lg"
              class="pl-10"
            />
            <v-list-item
              v-if="canViewDesignSystems"
              title="Design Systems"
              to="/settings/design-systems"
              rounded="lg"
              class="pl-10"
            />
            <v-list-item
              v-if="canViewAgentPrompts"
              title="Agent Prompts"
              to="/settings/agent-prompts"
              rounded="lg"
              class="pl-10"
            />
          </v-list-group>
        </v-list>

        <!-- User menu -->
        <div class="px-3 pb-3">
          <v-menu location="top start" :offset="[0, 4]">
            <template #activator="{ props }">
              <div
                v-bind="props"
                class="user-menu d-flex align-center ga-2 pa-2 rounded-lg cursor-pointer"
              >
                <v-avatar size="32" color="primary" variant="tonal">
                  <span class="text-caption font-weight-bold">{{ userInitials }}</span>
                </v-avatar>
                <div class="flex-grow-1 overflow-hidden">
                  <div class="text-body-2 font-weight-medium text-truncate">
                    {{ authStore.user?.name || 'User' }}
                  </div>
                  <div class="text-caption text-medium-emphasis text-truncate">
                    {{ authStore.user?.email || '' }}
                  </div>
                </div>
                <v-icon icon="mdi-chevron-up" size="16" class="text-medium-emphasis" />
              </div>
            </template>

            <v-list density="compact" min-width="200">
              <v-list-item
                prepend-icon="mdi-account-edit-outline"
                title="Customize Character"
                to="/character-select"
              />
              <v-list-item
                prepend-icon="mdi-logout"
                title="Sign out"
                @click="handleLogout"
              />
            </v-list>
          </v-menu>
        </div>
      </template>
    </v-navigation-drawer>

    <!-- Main content -->
    <v-main class="app-main">
      <div class="app-scroll">
        <router-view />
      </div>
    </v-main>

    <!-- Real-time XP toast notifications -->
    <XPToast
      :toasts="xpToasts"
      @dismiss="xpDismiss"
    />
  </v-app>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import BodhigroveLogo from '@/components/common/BodhigroveLogo.vue'
import NotificationBell from '@/components/common/NotificationBell.vue'
import XPToast from '@/components/common/XPToast.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useXPSocket } from '@/composables/useXPSocket'

const router = useRouter()
const authStore = useAuthStore()

// Real-time XP notifications — runs for all authenticated pages
const { toasts: xpToasts, dismissToast: xpDismiss } = useXPSocket()
const {
  canApprove,
  canManageMembers,
  canViewSettings,
  canViewConnections,
  canViewDesignSystems,
  canViewAgentPrompts,
} = usePermissions()

const userInitials = computed(() => {
  const name = authStore.user?.name || ''
  return name
    .split(' ')
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2) || '?'
})

onMounted(() => {
  if (authStore.isAuthenticated && !authStore.user) {
    authStore.fetchUser()
  }
})

function handleLogout(): void {
  authStore.logout()
  router.push({ name: 'login' })
}
</script>

<style scoped>
.app-sidebar {
  border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
}

.app-main {
  height: 100vh;
  max-height: 100vh;
}

.app-scroll {
  height: 100%;
  overflow-y: auto;
}

.user-menu {
  transition: background-color 0.15s ease;
}

.user-menu:hover {
  background: rgba(255, 255, 255, 0.06);
}
</style>
