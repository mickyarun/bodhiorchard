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

<!-- Sign-in: the form on the left, the navy brand panel on the right.
     Below 960px the panel is dropped and the form takes the full width. -->
<template>
  <div class="login-shell">
    <main class="login-shell__main">
      <div class="login-shell__inner">
        <BrandLogo :size="34" />

        <header class="login-shell__head">
          <h1 class="login-shell__title bo-display">Sign in</h1>
          <p class="login-shell__lede">Welcome back to your workspace.</p>
        </header>

        <AppCallout v-if="errorMessage" variant="error" role="alert">
          {{ errorMessage }}
          <template #actions>
            <v-btn
              icon="mdi-close"
              aria-label="Dismiss"
              variant="text"
              size="x-small"
              @click="dismissError"
            />
          </template>
        </AppCallout>

        <v-form class="login-shell__form" @submit.prevent="handleLogin">
          <v-text-field
            v-model="email"
            label="Work email"
            type="email"
            autocomplete="email"
            autofocus
            :rules="[rules.required, rules.email]"
          />
          <PasswordField
            v-model="password"
            label="Password"
            autocomplete="current-password"
            :rules="[rules.required]"
          />
          <v-btn
            type="submit"
            color="primary"
            variant="flat"
            block
            size="large"
            :loading="loading"
            :disabled="!email.trim() || !password"
          >
            Sign in
          </v-btn>
        </v-form>

        <p class="login-shell__note">
          New here? Ask your workspace admin for an invite. Self-hosted: your data stays on your
          own servers.
        </p>
      </div>
    </main>
    <LoginBrandPanel class="login-shell__panel" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import api from '@/services/api'
import AppCallout from '@/components/common/AppCallout.vue'
import BrandLogo from '@/components/common/BrandLogo.vue'
import PasswordField from '@/components/common/PasswordField.vue'
import LoginBrandPanel from '@/components/auth/LoginBrandPanel.vue'
import { afterSignIn } from '@/utils/afterSignIn'

const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const loading = ref(false)
const orgSlug = ref('')
// Set when the workspace couldn't be looked up, so a submit says why
// nothing happened instead of doing nothing.
const unreachable = ref(false)

const UNREACHABLE_MESSAGE = "Can't reach Glideship right now. Check your connection and reload."

const errorMessage = computed(
  () => authStore.loginError ?? (unreachable.value ? UNREACHABLE_MESSAGE : null),
)

const rules = {
  required: (v: string) => !!v?.trim() || 'Required',
  email: (v: string) => /.+@.+\..+/.test(v) || 'Enter a valid email',
}

onMounted(async () => {
  try {
    const { data } = await api.get('/setup/status')
    if (!data.is_setup_complete) {
      router.replace({ name: 'setup' })
      return
    }
    if (data.org_slug) {
      orgSlug.value = data.org_slug
    }
  } catch {
    // Backend unreachable: say so if they try to sign in.
  }
})

function dismissError(): void {
  authStore.loginError = null
  unreachable.value = false
}

async function handleLogin(): Promise<void> {
  if (!email.value.trim() || !password.value) return
  if (!orgSlug.value) {
    unreachable.value = true
    return
  }
  unreachable.value = false
  loading.value = true
  const success = await authStore.login(email.value.trim(), password.value, orgSlug.value)
  loading.value = false
  if (success) {
    router.push(authStore.mustChangePassword ? { name: 'change-password' } : afterSignIn(authStore.user))
  }
}
</script>

<style scoped>
.login-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  background: rgb(var(--v-theme-background));
  color: rgb(var(--v-theme-on-background));
}

.login-shell__main {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-xl, 3rem) var(--space-md, 1.5rem);
}

.login-shell__inner {
  width: 100%;
  max-width: 380px;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.login-shell__head {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.login-shell__title {
  margin: 0;
  font-size: 28px;
  line-height: 34px;
  font-weight: 600;
}

.login-shell__lede {
  margin: 0;
  font-size: 15px;
  color: rgb(var(--v-theme-muted));
}

.login-shell__form {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.login-shell__note {
  margin: 0;
  font-size: 13px;
  line-height: 19px;
  color: rgb(var(--v-theme-muted));
}

@media (max-width: 959px) {
  .login-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .login-shell__panel {
    display: none;
  }

  .login-shell__main {
    align-items: flex-start;
    padding: var(--space-xl, 3rem) var(--space-sm, 1rem);
  }

  .login-shell__inner {
    max-width: 420px;
  }
}
</style>
