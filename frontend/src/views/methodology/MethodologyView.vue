<template>
  <v-app>
    <!-- Top header bar -->
    <v-app-bar flat color="surface" density="compact" class="methodology-appbar">
      <div class="d-flex align-center justify-space-between w-100 px-4">
        <BodhigroveLogo :size="28" />
        <v-btn
          v-if="!isLoggedIn"
          color="primary"
          variant="flat"
          prepend-icon="mdi-login"
          @click="router.push({ name: 'login' })"
        >
          Login
        </v-btn>
        <v-btn
          v-else
          color="primary"
          variant="flat"
          prepend-icon="mdi-view-dashboard-outline"
          @click="router.push({ name: 'dashboard' })"
        >
          Go to Dashboard
        </v-btn>
      </div>
    </v-app-bar>

    <v-main>
      <div class="pa-6" style="max-width: 1100px; margin: 0 auto;">
        <MethodologyStep @start-building="handleStartBuilding" />
      </div>
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import BodhigroveLogo from '@/components/common/BodhigroveLogo.vue'
import MethodologyStep from '@/views/setup/steps/MethodologyStep.vue'

const router = useRouter()
const isLoggedIn = computed(() => !!localStorage.getItem('bodhigrove_token'))

function handleStartBuilding(): void {
  if (isLoggedIn.value) {
    router.push({ name: 'dashboard' })
  } else {
    router.push({ name: 'login' })
  }
}
</script>

<style scoped>
.methodology-appbar {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
}
</style>
