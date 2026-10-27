// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import type { StepDefinition } from '@/types/setup'

// The setup wizard's steps, in order. The index of each entry is the step
// number the setup store tracks, so keep this list and the store in step.
export const SETUP_STEPS: readonly StepDefinition[] = [
  { key: 'welcome', title: 'Welcome', description: 'What Glideship does' },
  { key: 'organization', title: 'Organization', description: 'Name your workspace' },
  { key: 'admin', title: 'Admin account', description: 'Create the first admin' },
  { key: 'ai-config', title: 'AI engine', description: 'Connect the coding agent' },
  { key: 'source-code', title: 'Repositories', description: 'Add the code to work on' },
  { key: 'review', title: 'Launch', description: 'Check and start' },
]
