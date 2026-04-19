// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * AgentWorkingPhrases — per-skill rotating status phrases.
 *
 * Each agent skill gets contextual phrases that cycle on the label
 * while the robot is working. Adds life and tells the user what
 * the agent is doing without real backend status updates.
 */

const PHRASES: Record<string, string[]> = {
  'product-manager': [
    'Analyzing requirements...', 'Drafting acceptance criteria...',
    'Reviewing edge cases...', 'Writing problem statement...',
    'Checking team capacity...', 'Scoping dependencies...',
    'Researching context...', 'Building PRD...',
  ],
  'tech-planner': [
    'Scanning codebase...', 'Mapping repo structure...',
    'Planning architecture...', 'Identifying impacted files...',
    'Estimating complexity...', 'Drafting tech spec...',
    'Analyzing dependencies...', 'Reviewing patterns...',
  ],
  'code-reviewer': [
    'Reading diff...', 'Checking code patterns...',
    'Reviewing test coverage...', 'Analyzing edge cases...',
    'Validating types...', 'Scanning for bugs...',
    'Checking style guide...', 'Reviewing imports...',
  ],
  'qa-engineer': [
    'Building test plan...', 'Analyzing test scenarios...',
    'Checking boundary cases...', 'Mapping test coverage...',
    'Writing assertions...', 'Reviewing risk areas...',
    'Planning regression tests...', 'Validating flows...',
  ],
  'designer': [
    'Scanning design system...', 'Building wireframe...',
    'Applying layout rules...', 'Setting up components...',
    'Reviewing spacing...', 'Generating HTML...',
    'Checking responsiveness...', 'Picking tokens...',
  ],
  'triage': [
    'Reading request...', 'Classifying priority...',
    'Checking existing BUDs...', 'Routing to team...',
    'Analyzing impact...', 'Drafting response...',
  ],
}

const DEFAULT_PHRASES = [
  'Processing...', 'Analyzing...', 'Working...',
  'Thinking...', 'Evaluating...', 'Computing...',
]

// Track current index per skill to cycle through phrases
const indices = new Map<string, number>()

/** Get the next working phrase for a skill, cycling through the list. */
export function getNextPhrase(skillSlug: string): string {
  const phrases = PHRASES[skillSlug] || DEFAULT_PHRASES
  const idx = (indices.get(skillSlug) || 0) % phrases.length
  indices.set(skillSlug, idx + 1)
  return phrases[idx]
}
