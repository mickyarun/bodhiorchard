// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SetupState } from '@/types/setup'
import {
  submitOrgInit as submitOrgInitAction,
  submitFinalize as submitFinalizeAction,
  type FinalizeResult,
  type OrgInitResult,
} from './setupSubmit'

export const useSetupStore = defineStore('setup', () => {
  const currentStep = ref(0)
  const isSubmitting = ref(false)
  const submitError = ref<string | null>(null)
  const scanId = ref<string | null>(null)
  const jobId = ref<string | null>(null)
  // Phase J — once submitOrgInit succeeds, the org+JWT are live and the
  // wizard's earlier-step values become read-only. Used by the wizard to
  // gate "Continue" on the AI Engine step (idempotent guard for
  // Back/Forward navigation) and by Org/Admin/AI steps to grey out their
  // fields once the org has been created.
  const orgInitDone = ref(false)
  // Phase O — true once submitFinalize succeeds. The wizard now fires
  // finalize on Continue out of the Source Code step, so the Review
  // step's Launch button must not re-POST. submitSetup short-circuits
  // when this is already true.
  const finalizeDone = ref(false)

  const state = ref<SetupState>({
    currentStep: 0,
    organization: {
      name: '',
      slug: '',
    },
    admin: {
      email: '',
      name: '',
      password: '',
    },
    sourceCode: {
      repos: [],
    },
    scan: {
      timeoutSeconds: 300,
      maxTurns: 40,
    },
    claude: {
      authMode: 'host',
      apiKey: '',
      initialized: false,
      testPassed: false,
      testedVersion: '',
    },
  })

  // Step layout (Phase K — dedicated Connect-GitHub step retired; see
  // SetupWizard.vue for matching constants):
  //   0 Welcome | 1 Org | 2 Admin | 3 AI | 4 Source code | 5 Review
  const totalSteps = 6

  const isFirstStep = computed(() => currentStep.value === 0)
  const isLastStep = computed(() => currentStep.value === totalSteps - 1)
  const progress = computed(() => ((currentStep.value + 1) / totalSteps) * 100)

  function generateSlug(name: string): string {
    return name
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, '')
      .replace(/\s+/g, '-')
      .replace(/-+/g, '-')
      .trim()
  }

  function validateOrganization(): boolean {
    const { name, slug } = state.value.organization
    if (!name.trim()) return false
    if (!slug.trim()) return false
    if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(slug) && slug.length > 1) return false
    return true
  }

  function validateAdmin(): boolean {
    const { email, name, password } = state.value.admin
    if (!name.trim()) return false
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return false
    if (password.length < 8) return false
    return true
  }

  function validateSourceCode(): boolean {
    const repos = state.value.sourceCode.repos
    if (repos.length === 0) return false
    // Local-path entries are the only ones that surface a manual branch
    // picker (Phase P), so they're the only ones we strictly require both
    // branches on. Bulk + github-clone auto-detect at add-time and the
    // wizard doesn't render UI for the user to fix develop separately.
    return repos.every((r) => {
      if (!r.mainBranch) return false
      const src = r.source ?? (r.gitHubFullName ? 'bulk' : 'github-clone')
      if (src !== 'local-path') return true
      return !!r.developBranch
    })
  }

  function validateCurrentStep(): boolean {
    switch (currentStep.value) {
      case 0: return true // Welcome
      case 1: return validateOrganization()
      case 2: return validateAdmin()
      case 3: return true // AI Config — no blocking validation
      case 4: return validateSourceCode()
      case 5: return true // Review
      default: return false
    }
  }

  function nextStep(): boolean {
    if (!validateCurrentStep()) return false
    if (currentStep.value < totalSteps - 1) {
      currentStep.value++
      state.value.currentStep = currentStep.value
    }
    return true
  }

  function prevStep(): void {
    if (currentStep.value > 0) {
      currentStep.value--
      state.value.currentStep = currentStep.value
    }
  }

  function goToStep(step: number): void {
    if (step >= 0 && step < totalSteps) {
      currentStep.value = step
      state.value.currentStep = step
    }
  }

  const submitCtx = { state, submitError, scanId, jobId }

  /**
   * Idempotent: subsequent calls return ``null`` once the org already
   * exists for this session (the wizard re-enters the trigger on
   * Back/Forward navigation). Callers that need to know whether an init
   * actually ran should also check ``orgInitDone``.
   */
  async function submitOrgInit(): Promise<OrgInitResult | null> {
    if (orgInitDone.value) return null
    const result = await submitOrgInitAction(submitCtx)
    if (result) {
      orgInitDone.value = true
    }
    return result
  }

  async function submitFinalize(): Promise<FinalizeResult | null> {
    if (finalizeDone.value) {
      return {
        jobId: jobId.value || undefined,
        scanId: scanId.value || undefined,
        isSetupComplete: true,
      }
    }
    const result = await submitFinalizeAction(submitCtx)
    if (result) finalizeDone.value = true
    return result
  }

  /**
   * DEPRECATED — kept for back-compat with single-shot wizards.
   * New flow: submitOrgInit() then submitFinalize().
   *
   * Phase J: ``submitOrgInit`` is now idempotent (returns ``null`` once
   * the org already exists this session). The shim treats that as a
   * success and proceeds to finalize, so callers that have already
   * invoked ``submitOrgInit`` separately keep working.
   */
  async function submitSetup(): Promise<boolean> {
    isSubmitting.value = true
    try {
      if (!orgInitDone.value) {
        const init = await submitOrgInit()
        if (!init) return false
      }
      const finalized = await submitFinalize()
      return finalized !== null
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    currentStep,
    state,
    isSubmitting,
    submitError,
    scanId,
    jobId,
    orgInitDone,
    finalizeDone,
    totalSteps,
    isFirstStep,
    isLastStep,
    progress,
    generateSlug,
    validateCurrentStep,
    nextStep,
    prevStep,
    goToStep,
    submitOrgInit,
    submitFinalize,
    submitSetup,
  }
})
