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

<!-- Sign-in, in the shared signed-out frame (AuthShell). -->
<template>
  <AuthShell title="Sign in" lede="Welcome back to your workspace.">
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

    <v-form class="login-form" @submit.prevent="handleLogin">
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

    <template #note>
      New here? Ask your workspace admin for an invite. Self-hosted: your data stays on your own
      servers.
    </template>
  </AuthShell>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import api from '@/services/api'
import AppCallout from '@/components/common/AppCallout.vue'
import PasswordField from '@/components/common/PasswordField.vue'
import AuthShell from '@/components/auth/AuthShell.vue'
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
.login-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
