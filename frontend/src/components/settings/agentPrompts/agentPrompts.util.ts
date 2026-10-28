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
 * Pure helpers for the Agent Prompts settings page: the per-agent visual
 * identity, the stable section order and the search/filter grouping.
 */

import { AGENT_TYPE_LABELS, type AgentSkill, type AgentType } from '@/stores/agentSkills'

export type SkillFilterMode = 'all' | 'custom' | 'modified'

export interface AgentGroup {
  agentType: AgentType
  skills: AgentSkill[]
}

// Visual identity per agent type — picked so each section is distinguishable
// at a glance even when scrolling fast. Colors map to Vuetify theme tokens.
const AGENT_ICONS: Record<AgentType, string> = {
  triage: 'mdi-magnify-scan',
  bud: 'mdi-clipboard-text-outline',
  status: 'mdi-pulse',
  standup: 'mdi-account-group-outline',
  learning: 'mdi-book-open-page-variant-outline',
  bugLinker: 'mdi-bug-outline',
  reassignment: 'mdi-account-switch-outline',
  skill: 'mdi-shield-check-outline',
  techPlan: 'mdi-vector-polyline',
  testPlan: 'mdi-test-tube',
  design: 'mdi-palette-outline',
  slackTriage: 'mdi-slack',
  slackFeatureQa: 'mdi-message-question-outline',
}

const AGENT_BLURBS: Record<AgentType, string> = {
  triage: 'Classifies inbound items into BUDs vs noise',
  bud: 'Writes the PRD when a BUD is opened',
  status: 'Surfaces DevOps and infra signals',
  standup: 'Generates the daily team digest',
  learning: 'Captures retrospective learnings',
  bugLinker: 'Matches incoming bugs to existing BUDs',
  reassignment: 'Suggests new owners when assignments stall',
  skill: 'Reviews code for the code-review stage',
  techPlan: 'Authors the technical architecture',
  testPlan: 'Designs test plans and QA cases',
  design: 'Produces visual designs from the design system',
  slackTriage: 'Triages Slack messages into actions',
  slackFeatureQa: 'Answers Slack questions about feature delivery, status, and ownership',
}

// Stable display order of agent types — matches the visible BUD lifecycle
// flow first (bud → design → tech_plan → test_plan → skill review), then the
// non-stage agents (triage, standup, etc.) below.
const AGENT_ORDER: AgentType[] = [
  'bud', 'design', 'techPlan', 'testPlan', 'skill',
  'triage', 'bugLinker', 'reassignment', 'standup',
  'learning', 'status', 'slackTriage', 'slackFeatureQa',
]

export function skillKey(skill: AgentSkill): string {
  return `${skill.skillSlug}__${skill.agentType}`
}

export function agentTypeLabel(at: AgentType): string {
  return AGENT_TYPE_LABELS[at] ?? at
}

export function agentIcon(at: AgentType): string {
  return AGENT_ICONS[at] ?? 'mdi-robot-outline'
}

export function agentBlurb(at: AgentType): string {
  return AGENT_BLURBS[at] ?? ''
}

function matchesFilter(skill: AgentSkill, mode: SkillFilterMode, q: string): boolean {
  if (mode === 'custom' && !skill.isCustom) return false
  if (mode === 'modified' && !skill.isCustomized) return false
  if (q) {
    const hay = `${skill.name} ${skill.description} ${skill.skillSlug}`.toLowerCase()
    if (!hay.includes(q)) return false
  }
  return true
}

// Seeded skills first, the default leading them, then alphabetical.
function compareSkills(a: AgentSkill, b: AgentSkill): number {
  if (a.isCustom !== b.isCustom) return a.isCustom ? 1 : -1
  if (a.isDefault !== b.isDefault) return a.isDefault ? -1 : 1
  return a.name.localeCompare(b.name)
}

/** Skills that pass the filter and search, grouped by agent in AGENT_ORDER. */
export function groupAgentSkills(
  skills: AgentSkill[],
  mode: SkillFilterMode,
  search: string,
): AgentGroup[] {
  const q = search.trim().toLowerCase()
  const grouped = new Map<AgentType, AgentSkill[]>()
  for (const s of skills) {
    if (!matchesFilter(s, mode, q)) continue
    const list = grouped.get(s.agentType) ?? []
    list.push(s)
    grouped.set(s.agentType, list)
  }
  const ordered: AgentGroup[] = []
  for (const at of AGENT_ORDER) {
    const group = grouped.get(at)
    if (group && group.length > 0) {
      ordered.push({ agentType: at, skills: group.sort(compareSkills) })
    }
  }
  return ordered
}
