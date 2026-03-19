import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { SetupState } from '@/types/setup'
import api from '@/services/api'
import { resetSetupCache } from '@/router'

export const useSetupStore = defineStore('setup', () => {
  const currentStep = ref(0)
  const isSubmitting = ref(false)
  const submitError = ref<string | null>(null)
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
      localPath: '',
      type: 'single-repo' as const,
    },
    integrations: {
      github: { enabled: false, pat: '' },
      slack: { enabled: false, botToken: '', signingSecret: '' },
    },
    llm: {
      provider: 'ollama',
      model: 'llama3:8b',
      baseUrl: 'http://localhost:11434',
      apiKey: '',
      premiumProvider: 'anthropic',
      premiumModel: 'claude-opus-4',
      embeddingProvider: 'ollama',
      embeddingModel: 'nomic-embed-text',
    },
    aiConfig: {
      preset: 'hybrid',
      ollamaUrl: 'http://localhost:11434',
      ollamaModel: 'llama3:8b',
      cloudProvider: 'anthropic',
      cloudApiKey: '',
      cloudModel: 'claude-sonnet-4-5-20250514',
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

  function validateIntegrations(): boolean {
    const { github, slack } = state.value.integrations
    if (github.enabled && !github.pat.trim()) return false
    if (slack.enabled && (!slack.botToken.trim() || !slack.signingSecret.trim())) return false
    return true
  }

  function validateAIConfig(): boolean {
    const ai = state.value.aiConfig
    if (ai.preset === 'local') {
      if (!ai.ollamaUrl.trim()) return false
    } else if (ai.preset === 'cloud') {
      if (!ai.cloudApiKey.trim()) return false
    } else if (ai.preset === 'hybrid') {
      if (!ai.cloudApiKey.trim()) return false
    } else if (ai.preset === 'claude-ollama') {
      if (!ai.ollamaUrl.trim()) return false
    }
    return true
  }

  function validateCurrentStep(): boolean {
    switch (currentStep.value) {
      case 0: return true // Methodology — always valid
      case 1: return true // Welcome — always valid
      case 2: return validateOrganization()
      case 3: return validateAdmin()
      case 4: return validateIntegrations() && validateAIConfig() // Connections
      case 5: return true // Review — always valid
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
        integrations: state.value.integrations,
        llm: state.value.llm,
        aiConfig: state.value.aiConfig,
      }

      const { data } = await api.post('/setup/initialize', payload)
      localStorage.setItem('flowdev_setup_complete', 'true')
      if (data.access_token) {
        localStorage.setItem('flowdev_token', data.access_token)
      }
      resetSetupCache()
      return true
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number; data?: { detail?: string; message?: string } } }
        // 409 = org slug already exists → setup was already completed
        if (axiosErr.response?.status === 409) {
          localStorage.setItem('flowdev_setup_complete', 'true')
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
