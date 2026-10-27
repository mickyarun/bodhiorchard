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
  <div>
    <!-- Fade between steps: a horizontal slide clips the outgoing card. -->
    <v-window v-model="setupStore.currentStep" :touch="false" class="setup-wizard__window">
      <v-window-item
        v-for="item in stepItems"
        :key="item.value"
        :value="item.value"
        transition="fade-transition"
        reverse-transition="fade-transition"
      >
        <WelcomeStep v-if="item.value === STEP_WELCOME" @get-started="setupStore.nextStep()" />
        <OrganizationStep v-else-if="item.value === STEP_ORG" />
        <AdminAccountStep v-else-if="item.value === STEP_ADMIN" />
        <AIConfigStep v-else-if="item.value === STEP_AI" />
        <SourceCodeStep v-else-if="item.value === STEP_SOURCE_CODE" mode="setup" />
        <ReviewStep v-else @launch="handleLaunch" />
      </v-window-item>
    </v-window>

    <AppCallout v-if="validationError" variant="warning" class="mb-4">
      {{ validationError }}
    </AppCallout>
    <AppCallout v-if="setupStore.submitError" variant="error" class="mb-4">
      {{ setupStore.submitError }}
    </AppCallout>

    <SetupFooter
      v-if="setupStore.currentStep > 0"
      :step="setupStore.currentStep"
      :busy="advancing"
      :back-locked="setupStore.finalizeDone"
      @back="setupStore.prevStep()"
      @next="handleNext"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useSetupStore } from '@/stores/setup'
import AppCallout from '@/components/common/AppCallout.vue'
import SetupFooter from '@/components/setup/SetupFooter.vue'
import { SETUP_STEPS } from '@/components/setup/setupSteps'
import WelcomeStep from './steps/WelcomeStep.vue'
import OrganizationStep from './steps/OrganizationStep.vue'
import AdminAccountStep from './steps/AdminAccountStep.vue'
import AIConfigStep from './steps/AIConfigStep.vue'
import SourceCodeStep from './steps/SourceCodeStep.vue'
import ReviewStep from './steps/ReviewStep.vue'

// Step layout (GitHub credentials are entered in the Source Code step's
// bulk-import tab; there is no separate GitHub step):
//   0 Welcome | 1 Org | 2 Admin | 3 AI | 4 Source code | 5 Review
const STEP_WELCOME = 0
const STEP_ORG = 1
const STEP_ADMIN = 2
const STEP_AI = 3
const STEP_SOURCE_CODE = 4
const STEP_REVIEW = 5
const stepItems = SETUP_STEPS.map((_, value) => ({ value }))

const setupStore = useSetupStore()
const router = useRouter()
const validationError = ref('')

// A validation message belongs to the step that raised it; drop it as soon
// as the user moves to another step (Back, Continue, or the step list).
watch(
  () => setupStore.currentStep,
  () => {
    validationError.value = ''
  },
)

const validationMessages: Record<number, string> = {
  [STEP_ORG]: 'Please fill in the organization name and slug.',
  [STEP_ADMIN]: 'Please complete all admin account fields with valid values.',
  [STEP_SOURCE_CODE]: 'Add at least one repository and map both main and develop branches.',
}

// True while Continue is waiting on the backend (creating the org, starting
// onboarding). Drives the button spinner and drops repeat clicks, so a
// double click can't send two create requests before the first returns.
const advancing = ref(false)

async function handleNext(): Promise<void> {
  if (advancing.value) return
  advancing.value = true
  try {
    await advance()
  } finally {
    advancing.value = false
  }
}

async function advance(): Promise<void> {
  // Leaving the AI Engine step is the canonical "create the org"
  // trigger. Once submitOrgInit succeeds the JWT is set into axios,
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

  // Leaving the Source Code step fires finalize so the wizard's
  // Continue button drives the bulk-onboard job. ReviewStep
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

<style scoped>
.setup-wizard__window {
  margin-bottom: var(--space-md, 1.5rem);
}
</style>
