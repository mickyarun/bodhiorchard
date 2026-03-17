<template>
  <v-app>
    <v-main class="setup-gradient d-flex align-center justify-center">
      <v-container class="d-flex flex-column align-center text-center" style="max-width: 600px;">
        <FlowDevLogo class="mb-8" />

        <v-card class="pa-8 card-border-dark w-100" color="surface">
          <v-icon icon="mdi-view-dashboard-outline" size="64" color="primary" class="mb-4" />
          <div class="text-h4 font-weight-bold mb-2">Dashboard Coming Soon</div>
          <div class="text-body-1 text-medium-emphasis mb-6">
            Your AI-powered SDLC is configured. The full dashboard is under development.
          </div>

          <v-chip color="primary" variant="tonal" prepend-icon="mdi-domain" class="mb-4">
            {{ orgName || 'Your Organization' }}
          </v-chip>

          <v-divider class="my-4" />

          <div class="text-body-2 text-medium-emphasis">
            Your AI agents are initializing. Check the backend logs for status.
          </div>
        </v-card>

        <v-btn
          variant="text"
          class="mt-6"
          prepend-icon="mdi-arrow-left"
          @click="backToSetup"
        >
          Back to Setup
        </v-btn>
      </v-container>
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSetupStore } from '@/stores/setup'
import FlowDevLogo from '@/components/common/FlowDevLogo.vue'

const setupStore = useSetupStore()
const orgName = computed(() => setupStore.state.organization.name)

function backToSetup(): void {
  // Clear setup state so the router guard allows navigation
  localStorage.removeItem('flowdev_setup_complete')
  localStorage.removeItem('flowdev_token')
  // Force full page reload to reset the in-memory guard cache
  window.location.href = '/setup'
}
</script>
