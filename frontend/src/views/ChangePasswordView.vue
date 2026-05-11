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
        <div class="text-h5 font-weight-bold mb-1 text-center">Change Password</div>
        <div class="text-body-2 text-medium-emphasis text-center mb-6">
          Your password must be changed before you can continue.
        </div>

        <v-alert v-if="errorMsg" type="error" variant="tonal" density="compact" class="mb-4">
          {{ errorMsg }}
        </v-alert>

        <v-form @submit.prevent="handleSubmit">
          <v-text-field
            v-model="newPassword"
            label="New Password"
            :type="showNew ? 'text' : 'password'"
            prepend-inner-icon="mdi-lock-outline"
            :append-inner-icon="showNew ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            density="compact"
            variant="outlined"
            class="mb-3"
            autofocus
            :rules="[v => v.length >= 8 || 'Min 8 characters']"
            @click:append-inner="showNew = !showNew"
          />

          <v-text-field
            v-model="confirmPassword"
            label="Confirm Password"
            :type="showConfirm ? 'text' : 'password'"
            prepend-inner-icon="mdi-lock-check-outline"
            :append-inner-icon="showConfirm ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            density="compact"
            variant="outlined"
            class="mb-4"
            :rules="[v => v === newPassword || 'Passwords do not match']"
            @click:append-inner="showConfirm = !showConfirm"
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

const router = useRouter()
const authStore = useAuthStore()

const newPassword = ref('')
const confirmPassword = ref('')
const showNew = ref(false)
const showConfirm = ref(false)
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
    router.push({ name: 'character-select' })
  } else {
    errorMsg.value = err
  }
}
</script>
