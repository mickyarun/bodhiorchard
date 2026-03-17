<template>
  <v-card class="pa-8 card-border-dark" color="surface">
    <div class="d-flex align-center ga-3 mb-6">
      <v-avatar color="primary" size="44">
        <v-icon icon="mdi-account-key-outline" size="24" />
      </v-avatar>
      <div>
        <div class="text-h5 font-weight-bold">Admin Account</div>
        <div class="text-body-2 text-medium-emphasis">Create the first admin user</div>
      </div>
    </div>

    <v-text-field
      v-model="setupStore.state.admin.name"
      label="Full Name"
      placeholder="Jane Doe"
      prepend-inner-icon="mdi-account-outline"
      class="mb-4"
      :rules="[rules.required]"
    />

    <v-text-field
      v-model="setupStore.state.admin.email"
      label="Email"
      placeholder="jane@acme.com"
      prepend-inner-icon="mdi-email-outline"
      type="email"
      class="mb-4"
      :rules="[rules.required, rules.email]"
    />

    <v-text-field
      v-model="setupStore.state.admin.password"
      label="Password"
      placeholder="Minimum 8 characters"
      prepend-inner-icon="mdi-lock-outline"
      :type="showPassword ? 'text' : 'password'"
      :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
      class="mb-1"
      :rules="[rules.required, rules.minLength]"
      @click:append-inner="showPassword = !showPassword"
    />

    <v-progress-linear
      :model-value="passwordStrength"
      :color="passwordStrengthColor"
      class="mb-1"
      height="4"
      rounded
    />
    <div class="text-caption text-medium-emphasis mb-4">
      Password strength: {{ passwordStrengthLabel }}
    </div>

    <v-text-field
      v-model="confirmPassword"
      label="Confirm Password"
      placeholder="Re-enter your password"
      prepend-inner-icon="mdi-lock-check-outline"
      :type="showConfirmPassword ? 'text' : 'password'"
      :append-inner-icon="showConfirmPassword ? 'mdi-eye-off' : 'mdi-eye'"
      :rules="[rules.required, rules.passwordMatch]"
      @click:append-inner="showConfirmPassword = !showConfirmPassword"
    />
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSetupStore } from '@/stores/setup'

const setupStore = useSetupStore()
const showPassword = ref(false)
const showConfirmPassword = ref(false)
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
