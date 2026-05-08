<template>
  <v-app>
    <!-- Sidebar -->
    <v-navigation-drawer
      v-model:rail="rail"
      permanent
      color="surface"
      :width="240"
      rail-width="68"
      expand-on-hover
      class="app-sidebar"
    >
      <div
        class="pa-4 pb-2 d-flex align-center"
        :class="rail ? 'justify-center' : 'justify-space-between'"
      >
        <BodhiorchardLogo :size="28" :show-text="!rail" />
        <NotificationBell v-if="!rail && authStore.user?.id" :user-id="authStore.user.id" />
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
          to="/bugs"
          rounded="lg"
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
              v-if="canViewCodeSettings"
              title="Code"
              to="/settings/code"
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
            <v-list-item
              v-if="canViewQAAutomation"
              title="QA Automation"
              to="/settings/qa-automation"
              rounded="lg"
              class="pl-10"
            />
            <v-list-item
              v-if="canViewPresenceSettings"
              title="Presence & Auto Mode"
              to="/settings/presence"
              rounded="lg"
              class="pl-10"
            />
            <v-list-item
              v-if="canViewJiraImport"
              title="Jira Import"
              to="/settings/jira-import"
              rounded="lg"
              class="pl-10"
            />
          </v-list-group>
        </v-list>

        <!-- User menu -->
        <div class="px-3 pb-3" :class="{ 'd-flex justify-center': rail }">
          <v-menu location="top start" :offset="[0, 4]">
            <template #activator="{ props }">
              <div
                v-bind="props"
                class="user-menu d-flex align-center ga-2 pa-2 rounded-lg cursor-pointer"
                :class="{ 'user-menu--rail': rail }"
              >
                <v-avatar size="32" color="primary" variant="tonal">
                  <span class="text-caption font-weight-bold">{{ userInitials }}</span>
                </v-avatar>
                <template v-if="!rail">
                  <div class="flex-grow-1 overflow-hidden">
                    <div class="text-body-2 font-weight-medium text-truncate">
                      {{ authStore.user?.name || 'User' }}
                    </div>
                    <div class="text-caption text-medium-emphasis text-truncate">
                      {{ authStore.user?.email || '' }}
                    </div>
                  </div>
                  <v-icon icon="mdi-chevron-up" size="16" class="text-medium-emphasis" />
                </template>
              </div>
            </template>

            <v-list density="compact" min-width="200">
              <v-list-item
                prepend-icon="mdi-account-circle-outline"
                title="My Profile"
                to="/profile"
              />
              <v-list-item
                prepend-icon="mdi-account-edit-outline"
                title="Customize Character"
                to="/character-select"
              />
              <!-- Self-service MCP token — any authenticated user, no
                   admin or settings permission required. Gives Claude
                   Code a personal token for commit attribution. -->
              <v-list-item
                prepend-icon="mdi-key-variant"
                title="MCP Token"
                to="/profile/mcp-token"
              />
              <v-divider class="my-1" />
              <v-list-item
                prepend-icon="mdi-logout"
                title="Sign out"
                @click="handleLogout"
              />
            </v-list>
          </v-menu>
        </div>

        <!-- Collapse / expand toggle — sticky bottom of the drawer. -->
        <v-divider />
        <div
          class="d-flex pa-1"
          :class="rail ? 'justify-center' : 'justify-end pe-2'"
        >
          <v-btn
            :icon="rail ? 'mdi-chevron-right' : 'mdi-chevron-left'"
            variant="text"
            size="small"
            density="comfortable"
            :title="rail ? 'Expand sidebar' : 'Collapse sidebar'"
            @click="toggleRail"
          />
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

    <!-- Race invite toast + watch banner — both mount layout-wide so they
         survive route changes while the user is signed in. -->
    <RaceInviteToast v-if="authStore.user?.id" />
    <RaceWatchBanner v-if="authStore.user?.id" />
  </v-app>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import BodhiorchardLogo from '@/components/common/BodhiorchardLogo.vue'
import NotificationBell from '@/components/common/NotificationBell.vue'
import XPToast from '@/components/common/XPToast.vue'
import RaceInviteToast from '@/components/race/RaceInviteToast.vue'
import RaceWatchBanner from '@/components/race/RaceWatchBanner.vue'
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
  canViewCodeSettings,
  canViewDesignSystems,
  canViewAgentPrompts,
  canViewQAAutomation,
  canViewPresenceSettings,
  canViewJiraImport,
} = usePermissions()

// Collapsed-sidebar preference, persisted across reloads. `expand-on-hover`
// on the drawer means even in rail mode the user can peek labels without
// flipping this flag.
const RAIL_KEY = 'bodhiorchard_sidebar_rail'
const rail = ref(localStorage.getItem(RAIL_KEY) === 'true')
watch(rail, (v) => localStorage.setItem(RAIL_KEY, String(v)))

function toggleRail(): void {
  rail.value = !rail.value
}

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
  /* 100vh on iOS Safari counts the URL/tab bar area, so content
     extends below the visible viewport. 100dvh resolves to the
     currently-visible height. Keep 100vh as a fallback — browsers
     that parse `dvh` (Safari 15.4+, Chrome 108+, Firefox 101+)
     win via the @supports block below. */
  height: 100vh;
  max-height: 100vh;
}

@supports (height: 100dvh) {
  .app-main {
    height: 100dvh;
    max-height: 100dvh;
  }
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
