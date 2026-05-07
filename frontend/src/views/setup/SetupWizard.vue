<template>
  <div>
    <StepIndicator
      :current-step="setupStore.currentStep"
      @go-to-step="setupStore.goToStep"
    />

    <v-window
      v-model="setupStore.currentStep"
      :touch="false"
      class="mb-6"
    >
      <v-window-item :value="STEP_WELCOME">
        <WelcomeStep @get-started="setupStore.nextStep()" />
      </v-window-item>

      <v-window-item :value="STEP_ORG">
        <OrganizationStep />
      </v-window-item>

      <v-window-item :value="STEP_ADMIN">
        <AdminAccountStep />
      </v-window-item>

      <v-window-item :value="STEP_AI">
        <AIConfigStep />
      </v-window-item>

      <v-window-item :value="STEP_SOURCE_CODE">
        <SourceCodeStep mode="setup" />
      </v-window-item>

      <v-window-item :value="STEP_REVIEW">
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
      v-if="setupStore.currentStep > 0"
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
import WelcomeStep from './steps/WelcomeStep.vue'
import OrganizationStep from './steps/OrganizationStep.vue'
import AdminAccountStep from './steps/AdminAccountStep.vue'
import AIConfigStep from './steps/AIConfigStep.vue'
import SourceCodeStep from './steps/SourceCodeStep.vue'
import ReviewStep from './steps/ReviewStep.vue'

// Step layout (Phase K — dedicated Connect-GitHub step retired; the
// bulk-import tab inside SourceCodeStep now owns the credential entry):
//   0 Welcome | 1 Org | 2 Admin | 3 AI | 4 Source code | 5 Review
const STEP_WELCOME = 0
const STEP_ORG = 1
const STEP_ADMIN = 2
const STEP_AI = 3
const STEP_SOURCE_CODE = 4
const STEP_REVIEW = 5

const setupStore = useSetupStore()
const router = useRouter()
const validationError = ref('')

const validationMessages: Record<number, string> = {
  [STEP_ORG]: 'Please fill in the organization name and slug.',
  [STEP_ADMIN]: 'Please complete all admin account fields with valid values.',
  [STEP_SOURCE_CODE]: 'Add at least one repository and map both main and develop branches.',
}

async function handleNext(): Promise<void> {
  // Phase J — leaving the AI Engine step is the canonical "create the
  // org" trigger. Once submitOrgInit succeeds the JWT is set into axios,
  // so every later step (Source Code → Bulk Import) works against a
  // real backend. submitOrgInit is idempotent on Back/Forward
  // navigation; subsequent calls no-op.
  if (setupStore.currentStep === STEP_AI && !setupStore.orgInitDone) {
    if (!setupStore.validateCurrentStep()) {
      validationError.value =
        validationMessages[setupStore.currentStep] || 'Please complete this step.'
      return
    }
    const result = await setupStore.submitOrgInit()
    if (!result && !setupStore.orgInitDone) {
      // submitError on the store is rendered below; don't double up
      // with the validation banner.
      validationError.value = ''
      return
    }
    validationError.value = ''
    setupStore.goToStep(STEP_SOURCE_CODE)
    return
  }

  // Phase O — leaving the Source Code step fires finalize so the
  // wizard's Continue button drives the bulk-onboard job. ReviewStep
  // becomes a launch confirmation screen that already has jobId/scanId
  // in flight by the time it renders.
  if (setupStore.currentStep === STEP_SOURCE_CODE) {
    if (!setupStore.validateCurrentStep()) {
      validationError.value =
        validationMessages[setupStore.currentStep] || 'Please complete this step.'
      return
    }
    const finalized = await setupStore.submitFinalize()
    if (!finalized) {
      validationError.value = ''
      return
    }
    validationError.value = ''
    setupStore.goToStep(STEP_REVIEW)
    return
  }

  const success = setupStore.nextStep()
  if (!success) {
    validationError.value =
      validationMessages[setupStore.currentStep] || 'Please complete this step.'
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
