// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Single source of truth for agent-character presentation text.
 *
 * Phrases and display names are identical on server and client — adding
 * a new skill slug here updates both without drift.
 *   - Server: `AgentActivitySim` picks phrases from PHRASES via its own
 *     per-agent cursor, assigns them to `AgentState.message`, and
 *     Colyseus syncs that string to clients.
 *   - Client: `AgentWorkingPhrases` keeps a per-skill cursor for the
 *     legacy (non-server-driven) code path. Both paths read from the
 *     same tables below.
 */

/** Rotating "thinking…" phrases shown above each working agent. */
export const PHRASES: Record<string, string[]> = {
  "product-manager": [
    "Analyzing requirements...", "Drafting acceptance criteria...",
    "Reviewing edge cases...", "Writing problem statement...",
    "Checking team capacity...", "Scoping dependencies...",
    "Researching context...", "Building PRD...",
  ],
  "tech-planner": [
    "Scanning codebase...", "Mapping repo structure...",
    "Planning architecture...", "Identifying impacted files...",
    "Estimating complexity...", "Drafting tech spec...",
    "Analyzing dependencies...", "Reviewing patterns...",
  ],
  "code-reviewer": [
    "Reading diff...", "Checking code patterns...",
    "Reviewing test coverage...", "Analyzing edge cases...",
    "Validating types...", "Scanning for bugs...",
    "Checking style guide...", "Reviewing imports...",
  ],
  "qa-engineer": [
    "Building test plan...", "Analyzing test scenarios...",
    "Checking boundary cases...", "Mapping test coverage...",
    "Writing assertions...", "Reviewing risk areas...",
    "Planning regression tests...", "Validating flows...",
  ],
  "designer": [
    "Scanning design system...", "Building wireframe...",
    "Applying layout rules...", "Setting up components...",
    "Reviewing spacing...", "Generating HTML...",
    "Checking responsiveness...", "Picking tokens...",
  ],
  "triage": [
    "Reading request...", "Classifying priority...",
    "Checking existing BUDs...", "Routing to team...",
    "Analyzing impact...", "Drafting response...",
  ],
}

/** Fallback phrases when the skill slug isn't in PHRASES. */
export const DEFAULT_PHRASES = [
  "Processing...", "Analyzing...", "Working...",
  "Thinking...", "Evaluating...", "Computing...",
]

/** Pretty name per skill slug. */
const SKILL_NAMES: Record<string, string> = {
  "product-manager": "Product Manager",
  "tech-planner": "Tech Planner",
  "code-reviewer": "Code Reviewer",
  "qa-engineer": "QA Engineer",
  "designer": "Designer",
  "triage": "Triage Agent",
  "backend-developer": "Backend Dev",
  "frontend-developer": "Frontend Dev",
}

/** Resolve a skill slug to a human-readable name, with a slug-prettify fallback. */
export function getSkillDisplayName(slug: string): string {
  return SKILL_NAMES[slug] ?? slug
    .replace(/-/g, " ")
    .replace(/\b\w/g, c => c.toUpperCase())
}
