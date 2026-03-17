<template>
  <div>
    <StepIndicator
      :current-step="setupStore.currentStep"
      @go-to-step="setupStore.goToStep"
    />

    <v-window v-model="setupStore.currentStep" class="mb-6">
      <v-window-item :value="0">
        <MethodologyStep @start-building="setupStore.nextStep()" />
      </v-window-item>

      <v-window-item :value="1">
        <WelcomeStep @get-started="setupStore.nextStep()" />
      </v-window-item>

      <v-window-item :value="2">
        <OrganizationStep />
      </v-window-item>

      <v-window-item :value="3">
        <AdminAccountStep />
      </v-window-item>

      <v-window-item :value="4">
        <IntegrationsStep />
      </v-window-item>

      <v-window-item :value="5">
        <ReviewStep @launch="handleLaunch" />
      </v-window-item>
    </v-window>

    <v-alert
      v-if="validationError"
      type="warning"
      variant="tonal"
      class="mb-4"
      closable
      @click:close="validationError = ''"
    >
      {{ validationError }}
    </v-alert>

    <v-alert
      v-if="setupStore.submitError"
      type="error"
      variant="tonal"
      class="mb-4"
      closable
    >
      {{ setupStore.submitError }}
    </v-alert>

    <div
      v-if="setupStore.currentStep > 1"
      class="d-flex justify-space-between align-center"
    >
      <v-btn
        variant="text"
        prepend-icon="mdi-arrow-left"
        :disabled="setupStore.isFirstStep"
        @click="setupStore.prevStep()"
      >
        Back
      </v-btn>

      <v-btn
        v-if="!setupStore.isLastStep"
        color="primary"
        append-icon="mdi-arrow-right"
        @click="handleNext"
      >
        Continue
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useSetupStore } from '@/stores/setup'
import StepIndicator from '@/components/setup/StepIndicator.vue'
import MethodologyStep from './steps/MethodologyStep.vue'
import WelcomeStep from './steps/WelcomeStep.vue'
import OrganizationStep from './steps/OrganizationStep.vue'
import AdminAccountStep from './steps/AdminAccountStep.vue'
import IntegrationsStep from './steps/IntegrationsStep.vue'
import ReviewStep from './steps/ReviewStep.vue'

const setupStore = useSetupStore()
const router = useRouter()
const validationError = ref('')

const validationMessages: Record<number, string> = {
  2: 'Please fill in the organization name and slug.',
  3: 'Please complete all admin account fields with valid values.',
  4: 'Please complete the configuration for enabled integrations and AI settings.',
}

function handleNext(): void {
  const success = setupStore.nextStep()
  if (!success) {
    validationError.value = validationMessages[setupStore.currentStep] || 'Please complete this step.'
  } else {
    validationError.value = ''
  }
}

async function handleLaunch(): Promise<void> {
  const success = await setupStore.submitSetup()
  if (success) {
    router.push('/dashboard')
  }
}
</script>
