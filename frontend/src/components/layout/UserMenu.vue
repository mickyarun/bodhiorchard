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

<!-- Signed-in user's menu: profile links, theme switch, sign out. -->
<template>
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

    <v-list density="compact" min-width="244">
      <!-- XP profile, garden character and MCP token are all
           engineering-workspace features. -->
      <template v-if="canAccessEngineering">
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
        <!-- Self-service MCP token: gives Claude Code a personal
             token for commit attribution. -->
        <v-list-item
          prepend-icon="mdi-key-variant"
          title="MCP Token"
          to="/profile/mcp-token"
        />
      </template>
      <!-- Self-service Slack notification opt-outs — any member,
           no permission gate. -->
      <v-list-item
        prepend-icon="mdi-bell-cog-outline"
        title="Notification Settings"
        to="/profile/notifications"
      />
      <div class="theme-pref px-3 pt-2 pb-1">
        <div class="text-caption text-medium-emphasis px-1 mb-1">Theme</div>
        <div class="theme-seg" role="radiogroup" aria-label="Theme">
          <button
            v-for="opt in THEME_OPTIONS"
            :key="opt.value"
            type="button"
            role="radio"
            :aria-checked="themePref === opt.value"
            class="theme-seg__btn"
            :class="{ 'theme-seg__btn--active': themePref === opt.value }"
            :title="opt.hint"
            @click.stop="setThemePref(opt.value)"
          >
            <v-icon :icon="opt.icon" size="15" />
            {{ opt.label }}
          </button>
        </div>
      </div>
      <v-divider class="my-1" />
      <v-list-item
        prepend-icon="mdi-logout"
        title="Sign out"
        @click="handleLogout"
      />
    </v-list>
  </v-menu>
</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePermissions } from '@/composables/usePermissions'
import { useThemePreference, type ThemePreference } from '@/composables/useThemePreference'

defineProps<{ rail: boolean }>()

const router = useRouter()
const authStore = useAuthStore()
const { canAccessEngineering } = usePermissions()

// Light/dark toggle (persisted to localStorage by the composable).
const { preference: themePref, setPreference: setThemePref } = useThemePreference()
const THEME_OPTIONS: { value: ThemePreference; label: string; icon: string; hint: string }[] = [
  { value: 'system', label: 'Auto', icon: 'mdi-brightness-auto', hint: 'Follow system' },
  { value: 'light', label: 'Light', icon: 'mdi-weather-sunny', hint: 'Light theme' },
  { value: 'dark', label: 'Dark', icon: 'mdi-weather-night', hint: 'Dark theme' },
]

const userInitials = computed(() => {
  const name = authStore.user?.name || ''
  return name
    .split(' ')
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2) || '?'
})

function handleLogout(): void {
  authStore.logout()
  // A full page load, as when a session expires (services/api.ts): every
  // store, socket and the 3D scene start empty, so nothing of this user's
  // (leave, HR records, approvals) is left for whoever signs in next.
  window.location.assign(router.resolve({ name: 'login' }).href)
}
</script>

<style scoped>
.user-menu {
  transition: background-color 0.15s ease;
}

.user-menu:hover {
  background: rgb(var(--v-theme-surface-bright));
}

/* Auto / Light / Dark segmented control in the user menu. */
.theme-seg {
  display: flex;
  gap: 2px;
  padding: 3px;
  background: rgb(var(--v-theme-surface-bright));
  border-radius: var(--radius-pill, 999px);
}
.theme-seg__btn {
  flex: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 5px 6px;
  border: none;
  background: transparent;
  border-radius: var(--radius-pill, 999px);
  color: rgb(var(--v-theme-on-surface-variant));
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s var(--ease-out, ease), color 0.15s var(--ease-out, ease);
}
.theme-seg__btn:hover:not(.theme-seg__btn--active) {
  color: rgb(var(--v-theme-on-surface));
}
.theme-seg__btn--active {
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-primary));
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.18);
}
.theme-seg__btn:focus-visible {
  outline: 2px solid var(--color-focus, rgb(var(--v-theme-primary)));
  outline-offset: 1px;
}
</style>
