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

<!-- The frame for the signed-out screens (sign-in, forced password change):
     logo, title and lede over the slotted form on the left, the navy brand
     panel on the right. Below 960px the panel is dropped and the form takes
     the full width. -->
<template>
  <div class="auth-shell">
    <main class="auth-shell__main">
      <div class="auth-shell__inner">
        <BrandLogo :size="34" />
        <header class="auth-shell__head">
          <h1 class="auth-shell__title bo-display">{{ title }}</h1>
          <p class="auth-shell__lede">{{ lede }}</p>
        </header>
        <slot />
        <p v-if="$slots.note" class="auth-shell__note">
          <slot name="note" />
        </p>
      </div>
    </main>
    <LoginBrandPanel class="auth-shell__panel" />
  </div>
</template>

<script setup lang="ts">
import BrandLogo from '@/components/common/BrandLogo.vue'
import LoginBrandPanel from '@/components/auth/LoginBrandPanel.vue'

defineProps<{
  title: string
  lede: string
}>()
</script>

<style scoped>
.auth-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  background: rgb(var(--v-theme-background));
  color: rgb(var(--v-theme-on-background));
}

.auth-shell__main {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-xl, 3rem) var(--space-md, 1.5rem);
}

.auth-shell__inner {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.auth-shell__head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.auth-shell__title {
  margin: 0;
  font-size: 28px;
  line-height: 34px;
  font-weight: 600;
}

.auth-shell__lede {
  margin: 0;
  font-size: 15px;
  color: rgb(var(--v-theme-muted));
}

.auth-shell__note {
  margin: 0;
  font-size: 13px;
  line-height: 19px;
  color: rgb(var(--v-theme-muted));
}

@media (max-width: 959px) {
  .auth-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .auth-shell__panel {
    display: none;
  }

  .auth-shell__main {
    align-items: flex-start;
    padding: var(--space-xl, 3rem) var(--space-sm, 1rem);
  }

  .auth-shell__inner {
    max-width: 420px;
  }
}
</style>
