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

<!-- Signed-in user's menu, opened from their avatar in the top bar:
     profile links, theme (Auto / Light / Dark), sign out. -->
<template>
  <v-menu location="bottom end" :offset="6">
    <template #activator="{ props }">
      <v-btn
        v-bind="props"
        icon
        variant="text"
        density="comfortable"
        :aria-label="`Account menu for ${authStore.user?.name || 'you'}`"
      >
        <AppMonogram :name="authStore.user?.name" :src="authStore.user?.avatar_url" :size="32" />
      </v-btn>
    </template>

    <v-list density="compact" min-width="260">
      <!-- Who you are; your photo is changed on My details, so the
           header goes there. -->
      <router-link
        v-if="authStore.user"
        :to="{ name: 'my-details' }"
        class="account-menu__who"
        role="listitem"
      >
        <AppMonogram :name="authStore.user.name" :src="authStore.user.avatar_url" :size="44" />
        <span class="account-menu__id">
          <span class="account-menu__name">{{ authStore.user.name }}</span>
          <span class="account-menu__email">{{ authStore.user.email }}</span>
          <span class="account-menu__photo">
            {{ authStore.user.avatar_url ? 'Change photo' : 'Add a photo' }}
          </span>
        </span>
      </router-link>
      <v-divider class="mb-1" />
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
      <div class="theme-pref px-3 pt-2 pb-1" role="listitem">
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
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import AppMonogram from '@/components/common/AppMonogram.vue'
import { useAuthStore } from '@/stores/auth'
import { usePermissions } from '@/composables/usePermissions'
import { useThemePreference, type ThemePreference } from '@/composables/useThemePreference'

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

function handleLogout(): void {
  authStore.logout()
  // A full page load, as when a session expires (services/api.ts): every
  // store, socket and the 3D scene start empty, so nothing of this user's
  // (leave, HR records, approvals) is left for whoever signs in next.
  window.location.assign(router.resolve({ name: 'login' }).href)
}
</script>

<style scoped>
.account-menu__who {
  display: flex;
  align-items: center;
  gap: 12px;
  max-width: 280px;
  margin: 0 4px 4px;
  padding: 8px 12px;
  border-radius: var(--radius-card);
  color: inherit;
  text-decoration: none;
}
.account-menu__who:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.account-menu__who:focus-visible {
  outline: 2px solid var(--color-focus, rgb(var(--v-theme-primary)));
  outline-offset: -2px;
}
.account-menu__id {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.account-menu__name {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.account-menu__photo {
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
}
.account-menu__email {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Auto / Light / Dark segmented control in the account menu. */
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
  /* The accent wash reads as selected on the track in both themes. */
  background: var(--color-accent-soft);
  color: var(--color-accent-text);
}
.theme-seg__btn:focus-visible {
  outline: 2px solid var(--color-focus, rgb(var(--v-theme-primary)));
  outline-offset: 1px;
}
</style>
