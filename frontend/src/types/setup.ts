export interface SetupRepoConfig {
  path: string
  mainBranch: string | null
  developBranch: string | null
}

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
    repos: SetupRepoConfig[]
  }
  scan: {
    timeoutSeconds: number
    maxTurns: number
  }
}

export interface StepDefinition {
  title: string
  icon: string
  key: string
}

export interface SetupChecklistStatus {
  orgCreated: boolean
  claudeCodeTested: boolean
  repoAdded: boolean
  scanComplete: boolean
  scanInProgress: boolean
  scanId: string | null
  scanProgress: number
  githubConnected: boolean
  slackConnected: boolean
  branchesMapped: boolean
  membersImported: boolean
  // True once the org has visited the QA automation settings page and
  // saved any value (even defaults). See backend/app/api/v1/setup.py.
  qaConfigured: boolean
}
