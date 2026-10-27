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
  <div class="setup-gradient d-flex flex-column" style="min-height: 100vh;">
    <v-container class="d-flex flex-column align-center justify-center flex-grow-1 py-8">
      <v-card color="surface" class="pa-8 w-100" max-width="420">
        <div class="text-h5 font-weight-bold bo-display mb-1 text-center">Change Password</div>
        <div class="text-body-2 text-medium-emphasis text-center mb-6">
          Your password must be changed before you can continue.
        </div>

        <v-alert v-if="errorMsg" type="error" variant="tonal" density="compact" class="mb-4">
          {{ errorMsg }}
        </v-alert>

        <v-form @submit.prevent="handleSubmit">
          <PasswordField
            v-model="newPassword"
            label="New password"
            prepend-inner-icon="mdi-lock-outline"
            autocomplete="new-password"
            density="compact"
            variant="outlined"
            class="mb-3"
            autofocus
            :rules="[(v: string) => v.length >= 8 || 'Min 8 characters']"
          />

          <PasswordField
            v-model="confirmPassword"
            label="Confirm password"
            prepend-inner-icon="mdi-lock-check-outline"
            autocomplete="new-password"
            density="compact"
            variant="outlined"
            class="mb-4"
            :rules="[(v: string) => v === newPassword || 'Passwords do not match']"
          />

          <v-btn
            type="submit"
            color="primary"
            block
            size="large"
            :loading="loading"
            :disabled="!canSubmit"
          >
            Set New Password
          </v-btn>
        </v-form>
      </v-card>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { afterSignIn } from '@/utils/afterSignIn'
import PasswordField from '@/components/common/PasswordField.vue'

const router = useRouter()
const authStore = useAuthStore()

const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMsg = ref('')

const canSubmit = computed(
  () => newPassword.value.length >= 8 && newPassword.value === confirmPassword.value,
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
