// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SetupState } from '@/types/setup'
import api from '@/services/api'
import { resetSetupCache } from '@/router'

export const useSetupStore = defineStore('setup', () => {
  const currentStep = ref(0)
  const isSubmitting = ref(false)
  const submitError = ref<string | null>(null)
  const scanId = ref<string | null>(null)

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
    },
  })

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
    // All repos must have branches mapped
    return repos.every(r => r.mainBranch && r.developBranch)
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

  async function submitSetup(): Promise<boolean> {
    isSubmitting.value = true
    submitError.value = null

    try {
      const payload = {
        organization: state.value.organization,
        admin: state.value.admin,
        sourceCode: state.value.sourceCode,
        scan: state.value.scan,
        claude: {
          authMode: state.value.claude.authMode,
          // Only send the key when we actually have one to store.
          apiKey: state.value.claude.authMode === 'api_key' && state.value.claude.apiKey
            ? state.value.claude.apiKey
            : null,
        },
      }

      const { data } = await api.post('/setup/initialize', payload)
      localStorage.setItem('bodhiorchard_setup_complete', 'true')
      if (data.access_token) {
        localStorage.setItem('bodhiorchard_token', data.access_token)
      }
      if (data.scanId) {
        // No localStorage write: consumers probe GET /v1/reposcanv2/scans/latest
        // on mount, so the backend is the single source of truth for
        // "is there a scan to show?".
        scanId.value = data.scanId
      }
      resetSetupCache()
      return true
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number; data?: { detail?: string; message?: string } } }
        if (axiosErr.response?.status === 409) {
          localStorage.setItem('bodhiorchard_setup_complete', 'true')
          resetSetupCache()
          return true
        }
        submitError.value =
          axiosErr.response?.data?.detail
          || axiosErr.response?.data?.message
          || 'Setup failed. Please try again.'
      } else {
        submitError.value = 'Network error. Please check your connection.'
      }
      return false
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
    totalSteps,
    isFirstStep,
    isLastStep,
    progress,
    generateSlug,
    validateCurrentStep,
    nextStep,
    prevStep,
    goToStep,
    submitSetup,
  }
})
