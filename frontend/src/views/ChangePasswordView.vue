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

<!-- Forced password change after signing in with a temporary password,
     in the shared signed-out frame (AuthShell). -->
<template>
  <AuthShell
    title="Change your password"
    lede="Your password must be changed before you can continue."
  >
    <AppCallout v-if="errorMsg" variant="error" role="alert">
      {{ errorMsg }}
    </AppCallout>

    <v-form class="change-password-form" @submit.prevent="handleSubmit">
      <PasswordField
        v-model="newPassword"
        label="New password"
        :hint="`At least ${PASSWORD_MIN_LENGTH} characters`"
        persistent-hint
        autocomplete="new-password"
        autofocus
        :rules="[passwordLengthRule]"
      />
      <PasswordField
        v-model="confirmPassword"
        label="Confirm password"
        autocomplete="new-password"
        :rules="[(v: string) => v === newPassword || 'Passwords do not match']"
      />
      <v-btn
        type="submit"
        color="primary"
        variant="flat"
        block
        size="large"
        :loading="loading"
        :disabled="!canSubmit"
      >
        Set new password
      </v-btn>
    </v-form>
  </AuthShell>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { afterSignIn } from '@/utils/afterSignIn'
import AppCallout from '@/components/common/AppCallout.vue'
import PasswordField from '@/components/common/PasswordField.vue'
import AuthShell from '@/components/auth/AuthShell.vue'
import { PASSWORD_MIN_LENGTH, passwordLengthRule } from '@/utils/passwordLength'

const router = useRouter()
const authStore = useAuthStore()

const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMsg = ref('')

const canSubmit = computed(
  () =>
    passwordLengthRule(newPassword.value) === true
    && newPassword.value === confirmPassword.value,
)

async function handleSubmit() {
  if (!canSubmit.value) return
  loading.value = true
  errorMsg.value = ''
  const err = await authStore.changePassword(newPassword.value)
  loading.value = false
  if (err === null) {
    // The profile couldn't load while the password change was pending; it
    // decides whether an engineer picks their avatar next.
    try {
      await authStore.fetchUser()
    } catch {
      // Without it, the router guard loads it on the way.
    }
    router.push(afterSignIn(authStore.user))
  } else {
    errorMsg.value = err
  }
}
</script>

<style scoped>
.change-password-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
</style>
