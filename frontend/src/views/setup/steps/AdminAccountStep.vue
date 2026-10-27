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
  <SetupStepHeader
    :step="2"
    title="Create the admin account"
    description="You'll sign in with this account. Invite the rest of your team once setup is done."
  />
  <v-card class="pa-6 card-border-dark" color="surface">
    <AppCallout v-if="setupStore.orgInitDone" variant="info" icon="mdi-lock-outline" class="mb-4">
      Locked after Continue — the admin account has already been created.
    </AppCallout>

    <v-text-field
      v-model="setupStore.state.admin.name"
      label="Full name"
      placeholder="Jane Doe"
      autocomplete="name"
      class="mb-2"
      :rules="[rules.required]"
      :readonly="setupStore.orgInitDone"
    />

    <v-text-field
      v-model="setupStore.state.admin.email"
      label="Work email"
      placeholder="jane@acme.com"
      type="email"
      autocomplete="email"
      class="mb-2"
      :rules="[rules.required, rules.email]"
      :readonly="setupStore.orgInitDone"
    />

    <PasswordField
      v-model="setupStore.state.admin.password"
      label="Password"
      hint="At least 8 characters"
      persistent-hint
      autocomplete="new-password"
      :rules="[rules.required, rules.minLength]"
      :readonly="setupStore.orgInitDone"
    />

    <div v-if="setupStore.state.admin.password" class="admin-step__strength" aria-live="polite">
      <v-progress-linear :model-value="passwordStrength" :color="passwordStrengthColor" height="4" rounded />
      <span>Strength: {{ passwordStrengthLabel }}</span>
    </div>

    <PasswordField
      v-model="confirmPassword"
      label="Confirm password"
      class="mt-4"
      autocomplete="new-password"
      :rules="[rules.required, rules.passwordMatch]"
      :readonly="setupStore.orgInitDone"
    />
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import PasswordField from '@/components/common/PasswordField.vue'
import SetupStepHeader from '@/components/setup/SetupStepHeader.vue'
import { useSetupStore } from '@/stores/setup'

const setupStore = useSetupStore()
const confirmPassword = ref('')

const passwordStrength = computed(() => {
  const pw = setupStore.state.admin.password
  if (!pw) return 0
  let score = 0
  if (pw.length >= 8) score += 25
  if (pw.length >= 12) score += 15
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score += 20
  if (/\d/.test(pw)) score += 20
  if (/[^a-zA-Z0-9]/.test(pw)) score += 20
  return Math.min(score, 100)
})

const passwordStrengthColor = computed(() => {
  if (passwordStrength.value < 30) return 'error'
  if (passwordStrength.value < 60) return 'warning'
  if (passwordStrength.value < 80) return 'info'
  return 'success'
})

const passwordStrengthLabel = computed(() => {
  if (passwordStrength.value < 30) return 'Weak'
  if (passwordStrength.value < 60) return 'Fair'
  if (passwordStrength.value < 80) return 'Good'
  return 'Strong'
})

const rules = {
  required: (v: string) => !!v?.trim() || 'This field is required',
  email: (v: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Enter a valid email address',
  minLength: (v: string) => v.length >= 8 || 'Password must be at least 8 characters',
  passwordMatch: (v: string) =>
    v === setupStore.state.admin.password || 'Passwords do not match',
}
</script>

<style scoped>
.admin-step__strength {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: var(--space-2xs, 0.5rem);
  font-size: 12px;
  color: rgb(var(--v-theme-muted));
}
</style>
