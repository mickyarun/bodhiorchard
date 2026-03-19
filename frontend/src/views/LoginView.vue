<template>
  <div class="setup-gradient d-flex flex-column" style="min-height: 100vh;">
    <v-container class="d-flex flex-column align-center justify-center flex-grow-1 py-8">
      <div class="mb-8">
        <FlowDevLogo />
      </div>

      <v-card color="surface" class="pa-8 w-100" max-width="420">
        <div class="text-h5 font-weight-bold mb-1 text-center">Welcome back</div>
        <div class="text-body-2 text-medium-emphasis text-center mb-6">
          Sign in to your FlowDev account
        </div>

        <v-alert
          v-if="authStore.loginError"
          type="error"
          variant="tonal"
          density="compact"
          class="mb-4"
          closable
          @click:close="authStore.loginError = null"
        >
          {{ authStore.loginError }}
        </v-alert>

        <v-form @submit.prevent="handleLogin">
          <v-text-field
            v-model="email"
            label="Email"
            type="email"
            prepend-inner-icon="mdi-email-outline"
            density="compact"
            variant="outlined"
            class="mb-3"
            autofocus
            :rules="[rules.required, rules.email]"
          />

          <v-text-field
            v-model="password"
            label="Password"
            :type="showPassword ? 'text' : 'password'"
            prepend-inner-icon="mdi-lock-outline"
            :append-inner-icon="showPassword ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
            density="compact"
            variant="outlined"
            class="mb-4"
            :rules="[rules.required]"
            @click:append-inner="showPassword = !showPassword"
          />

          <v-btn
            type="submit"
            color="primary"
            block
            size="large"
            :loading="loading"
            :disabled="!email.trim() || !password"
          >
            Sign In
          </v-btn>
        </v-form>
      </v-card>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import api from '@/services/api'
import FlowDevLogo from '@/components/common/FlowDevLogo.vue'

const router = useRouter()
const authStore = useAuthStore()

const email = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const orgSlug = ref('')

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
    // Backend unreachable
  }
})

async function handleLogin(): Promise<void> {
  if (!email.value.trim() || !password.value || !orgSlug.value) return
  loading.value = true
  const success = await authStore.login(email.value.trim(), password.value, orgSlug.value)
  loading.value = false
  if (success) {
    router.push({ name: 'dashboard' })
  }
}
</script>
