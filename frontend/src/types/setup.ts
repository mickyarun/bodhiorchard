export type AIPreset = 'local' | 'cloud' | 'hybrid' | 'claude-ollama'

export interface AIConfigState {
  preset: AIPreset
  ollamaUrl: string
  cloudProvider: 'anthropic' | 'openai'
  cloudApiKey: string
  cloudModel: string
  ollamaModel: string
}

export type SourceCodeType = 'workspace' | 'single-repo'

export interface SetupState {
  currentStep: number
  organization: {
    name: string
    slug: string
  }
  admin: {
    email: string
    name: string
    password: string
  }
  sourceCode: {
    localPath: string
    type: SourceCodeType
  }
  integrations: {
    github: { enabled: boolean; pat: string }
    slack: { enabled: boolean; botToken: string; signingSecret: string }
  }
  llm: {
    provider: 'ollama' | 'openai' | 'anthropic'
    model: string
    baseUrl: string
    apiKey: string
    premiumProvider: 'ollama' | 'openai' | 'anthropic'
    premiumModel: string
    embeddingProvider: 'ollama' | 'openai' | 'sentence-transformers'
    embeddingModel: string
  }
  aiConfig: AIConfigState
}

export interface StepDefinition {
  title: string
  icon: string
  key: string
}
