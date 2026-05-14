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

/**
 * Seed prompt for the "Enrich with AI" button on Jira-imported BUDs.
 *
 * Lives in its own module so the prompt text — which is product-facing
 * copy, not orchestration code — can be edited without touching the
 * chat composable.
 */
export const JIRA_ENRICH_PROMPT
  = 'This BUD was imported from Jira with minimal description. '
  + 'DO NOT update the content yet. Instead, put your clarifying questions '
  + 'directly in the "reply" field and set "updated_content" to null. '
  + 'Ask me 2-3 questions about: what this feature does, who it\'s for, '
  + 'acceptance criteria, and edge cases. I will answer, then you write the PRD.'
