<template>
  <div class="login-container">
    <h1>TaskFlow Login</h1>
    <form @submit.prevent="handleLogin">
      <div class="form-group">
        <label for="email">Email</label>
        <input id="email" v-model="email" type="email" required />
      </div>
      <div class="form-group">
        <label for="password">Password</label>
        <input id="password" v-model="password" type="password" required />
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <button type="submit" :disabled="loading">
        {{ loading ? 'Logging in...' : 'Login' }}
      </button>
      <router-link to="/register">Create an account</router-link>
      <router-link to="/forgot-password">Forgot password?</router-link>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/services/api'

const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.post('/auth/login', {
      email: email.value,
      password: password.value,
    })
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    router.push('/tasks')
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } } }
    error.value = axiosErr?.response?.data?.detail || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>
