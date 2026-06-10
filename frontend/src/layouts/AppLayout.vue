<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<template>
  <v-app>
    <!-- Sidebar -->
    <v-navigation-drawer
      v-model:rail="rail"
      permanent
      color="surface"
      :width="240"
      rail-width="68"
      :expand-on-hover="!notificationMenuOpen"
      class="app-sidebar"
    >
      <div
        class="pa-4 pb-2 d-flex align-center"
        :class="rail ? 'justify-center' : 'justify-space-between'"
      >
        <BodhiorchardLogo :size="28" :show-text="!rail" />
        <!-- v-show (not v-if) so the menu stays mounted even when the
             drawer briefly collapses to rail — moving the mouse to a
             dropdown item shouldn't unmount its trigger. The drawer
             also disables ``expand-on-hover`` while the menu is open
             (see ``notificationMenuOpen`` above) so the user can
             actually reach the dropdown without it dismissing. -->
        <NotificationBell
          v-show="!rail && authStore.user?.id"
          :user-id="authStore.user?.id || ''"
          @update:menu-open="notificationMenuOpen = $event"
        />
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
          prepend-icon="mdi-book-open-page-variant-outline"
          title="Learnings"
          to="/learnings"
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
            <!-- MCP Connect is self-service (any authenticated user can
                 mint / revoke their own tokens); no canView* gate. -->
            <v-list-item
              title="MCP Connect"
              to="/settings/mcp-connect"
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
      <!-- Route-navigation progress. Fixed to the top of the viewport so it
           reads as a global "the app is working" cue the instant a link is
           clicked — covering the lazy-chunk download that heavy views can't
           show feedback for until after they mount. -->
      <v-progress-linear
        v-if="navigating"
        indeterminate
        color="secondary"
        height="4"
        class="route-progress"
      />
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

    <!-- Cross-BUD job-completion toast. Surfaces when a chat / agent
         job finishes for a BUD the user is NOT currently on. The
         "snapped back to previous BUD" bug was *perceived* as
         auto-nav; replacing implicit jumps with this explicit Review
         CTA closes that class of complaint. Reads the existing
         notifications store, no extra socket subscriptions. -->
    <ChatCompletionToast v-if="authStore.user?.id" />

    <!-- Yield-offer reject / reassign confirmation dialogs. Lifted out
         of NotificationBell so the bell stays single-root and v-show
         on it doesn't trip Vue's "runtime directive on fragment" warn.
         The shared composable wires the bell-row triggers to these
         modals; v-dialog teleports to body so co-location doesn't
         matter for the rendered DOM. -->
    <YieldOfferDialogs v-if="authStore.user?.id" />
  </v-app>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import BodhiorchardLogo from '@/components/common/BodhiorchardLogo.vue'
import NotificationBell from '@/components/common/NotificationBell.vue'
import YieldOfferDialogs from '@/components/common/YieldOfferDialogs.vue'
import XPToast from '@/components/common/XPToast.vue'
import ChatCompletionToast from '@/components/common/ChatCompletionToast.vue'
import RaceInviteToast from '@/components/race/RaceInviteToast.vue'
import RaceWatchBanner from '@/components/race/RaceWatchBanner.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useXPSocket } from '@/composables/useXPSocket'
import { useNavigationProgress } from '@/composables/useNavigationProgress'

const router = useRouter()
const authStore = useAuthStore()

// Driven by the router guards — true while any route navigation resolves.
const { navigating } = useNavigationProgress()

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

// While the notification bell's dropdown is open, freeze the drawer's
// auto-collapse behaviour. Without this, moving the mouse off the
// drawer to click a dropdown item collapses the drawer (rail mode),
// which unmounts the bell trigger and dismisses the menu before the
// click lands.
const notificationMenuOpen = ref(false)
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
  /* Positioning context for the absolutely-positioned route progress bar
     so it pins to the top of the content area, not the whole viewport. */
  position: relative;
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

/* Pin the bar to the top of the main content area, above scrolled
   content, without participating in layout flow (so it never shifts the
   page as it appears/disappears). */
.route-progress {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 2000;
}

.user-menu {
  transition: background-color 0.15s ease;
}

.user-menu:hover {
  background: rgba(255, 255, 255, 0.06);
}
</style>
