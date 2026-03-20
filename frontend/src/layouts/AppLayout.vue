<template>
  <v-app>
    <!-- Sidebar -->
    <v-navigation-drawer permanent color="surface" width="240" class="app-sidebar">
      <div class="pa-4 pb-2">
        <FlowDevLogo :size="28" />
      </div>

      <v-list density="compact" nav class="px-2">
        <v-list-item
          prepend-icon="mdi-view-dashboard-outline"
          title="Dashboard"
          to="/dashboard"
          rounded="lg"
        />
        <v-list-item
          prepend-icon="mdi-file-document-outline"
          title="PRDs"
          to="/prds"
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
          prepend-icon="mdi-account-group-outline"
          title="Team"
          to="/teams"
          rounded="lg"
        />
      </v-list>

      <template #append>
        <v-divider class="mb-2" />
        <v-list density="compact" nav class="px-2 pb-2">
          <v-list-item
            prepend-icon="mdi-cog-outline"
            title="Settings"
            to="/settings"
            rounded="lg"
          />
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
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import FlowDevLogo from '@/components/common/FlowDevLogo.vue'

const router = useRouter()
const authStore = useAuthStore()

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

.user-menu {
  transition: background-color 0.15s ease;
}

.user-menu:hover {
  background: rgba(255, 255, 255, 0.06);
}
</style>
