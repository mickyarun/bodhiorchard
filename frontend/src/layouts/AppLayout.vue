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
    <!-- Phones get a top bar; the sidebar opens over the page from its
         menu button instead of taking a third of the screen. -->
    <MobileTopBar v-if="compact" v-model:drawer="overlayOpen" />

    <!-- Sidebar -->
    <v-navigation-drawer
      :model-value="compact ? overlayOpen : true"
      :rail="rail"
      :permanent="!compact"
      :temporary="compact"
      color="surface"
      :width="248"
      rail-width="68"
      :expand-on-hover="!compact"
      class="app-sidebar"
      @update:model-value="overlayOpen = $event"
      @update:rail="onRailHover"
    >
      <SidebarHead v-if="!compact" :collapsed="collapsed" />

      <v-list density="compact" nav class="px-2">
        <!-- Phones have the bell in the top bar. -->
        <NotificationBell v-if="!compact && authStore.user?.id" :user-id="authStore.user.id" variant="nav" />
        <EngineeringNav v-if="canAccessEngineering" :rail="collapsed" />
        <PeopleNav :rail="collapsed" :show-heading="canAccessEngineering" />
      </v-list>

      <template #append>
        <v-divider class="mb-2" />
        <v-list density="compact" nav class="px-2 pb-2">
          <v-list-item
            v-if="canAccessEngineering && canManageMembers"
            prepend-icon="mdi-account-group-outline"
            title="Members"
            to="/members"
            rounded="lg"
          />
          <SettingsNav />
        </v-list>

        <UserMenu :rail="collapsed" />

        <v-divider />
        <SidebarFoot :rail="rail" :can-rail="!compact" @toggle-rail="toggleRail" />
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

    <EngineeringOverlays v-if="authStore.user?.id && canAccessEngineering" />
  </v-app>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import EngineeringNav from '@/components/layout/EngineeringNav.vue'
import EngineeringOverlays from '@/components/layout/EngineeringOverlays.vue'
import MobileTopBar from '@/components/layout/MobileTopBar.vue'
import NotificationBell from '@/components/common/NotificationBell.vue'
import PeopleNav from '@/components/layout/PeopleNav.vue'
import SettingsNav from '@/components/layout/SettingsNav.vue'
import SidebarFoot from '@/components/layout/SidebarFoot.vue'
import SidebarHead from '@/components/layout/SidebarHead.vue'
import UserMenu from '@/components/layout/UserMenu.vue'
import { useAppDrawer } from '@/composables/useAppDrawer'
import { usePermissions } from '@/composables/usePermissions'
import { useNavigationProgress } from '@/composables/useNavigationProgress'

const authStore = useAuthStore()
const { canAccessEngineering, canManageMembers } = usePermissions()

// Driven by the router guards — true while any route navigation resolves.
const { navigating } = useNavigationProgress()

// Rail on wide screens (hovering expands it over the page), an overlay
// opened from the top bar on phones and small tablets. `collapsed` is the
// rail as drawn: everything inside lays out from it.
const { compact, rail, collapsed, overlayOpen, toggleRail, onRailHover } = useAppDrawer()

onMounted(() => {
  if (authStore.isAuthenticated && !authStore.user) {
    authStore.fetchUser()
  }
})
</script>

<style scoped>
.app-sidebar {
  border-right: 1px solid rgb(var(--v-theme-rule)) !important;
}

/* Nav rhythm: quiet by default; the active item is a soft blue wash with
   blue text, so the current section reads instantly without shouting.
   Motion is colour only. */
.app-sidebar :deep(.v-list-item) {
  margin-block: 1px;
  min-height: 36px;
  transition: background-color var(--dur-short, 150ms) var(--ease-out, ease),
              color var(--dur-short, 150ms) var(--ease-out, ease);
}

.app-sidebar :deep(.v-list-item .v-list-item-title) {
  font-size: 14px;
}

.app-sidebar :deep(.v-list-item:not(.v-list-item--active):hover) {
  background: rgb(var(--v-theme-surface-bright));
}

.app-sidebar :deep(.v-list-item--active) {
  color: var(--color-accent-text, rgb(var(--v-theme-primary)));
  background: var(--color-accent-soft, rgba(var(--v-theme-primary), 0.14));
}

/* Vuetify paints its own overlay on active items; the wash above replaces it. */
.app-sidebar :deep(.v-list-item--active > .v-list-item__overlay) {
  opacity: 0;
}

.app-sidebar :deep(.v-list-item--active .v-list-item-title) {
  font-weight: 500;
}

.app-sidebar :deep(.v-list-item--active .v-icon) {
  color: var(--color-accent-text, rgb(var(--v-theme-primary)));
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
</style>
