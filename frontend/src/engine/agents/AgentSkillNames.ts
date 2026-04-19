// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * AgentSkillNames — maps skill_slug to display-friendly names.
 */

const NAMES: Record<string, string> = {
  'product-manager': 'Product Manager',
  'tech-planner': 'Tech Planner',
  'code-reviewer': 'Code Reviewer',
  'qa-engineer': 'QA Engineer',
  'designer': 'Designer',
  'triage': 'Triage Agent',
  'backend-developer': 'Backend Dev',
  'frontend-developer': 'Frontend Dev',
}

export function getSkillDisplayName(slug: string): string {
  return NAMES[slug] || slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}
