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

// Shared marketing constants + copy for the landing site. Dependency-free.
// Copy is drawn from the real product positioning (README / methodology) — no
// invented metrics or testimonials.

export const GITHUB_URL = 'https://github.com/mickyarun/bodhiorchard'
export const SITE_TAGLINE = 'Build well. Then go outside.'

export interface Highlight {
  icon: string
  title: string
  body: string
  to: string
}

export const HOME_HIGHLIGHTS: Highlight[] = [
  {
    icon: 'mdi-file-edit-outline',
    title: 'AI drafts, you decide',
    body: 'Agents draft requirements, specs, and tests with full codebase context. Humans review, refine, and steer at every phase.',
    to: '/methodology',
  },
  {
    icon: 'mdi-chart-timeline-variant',
    title: 'Predictions, not poker',
    body: 'AI-PERT + Monte Carlo cycle-time forecasts replace story points and planning poker with probabilistic delivery dates.',
    to: '/methodology',
  },
  {
    icon: 'mdi-file-document-check-outline',
    title: 'One BUD per feature',
    body: 'Spec, tech spec, test plan, acceptance criteria, and full history live in a single living document — not scattered tickets.',
    to: '/platform',
  },
  {
    icon: 'mdi-database-sync-outline',
    title: 'Knowledge that stays current',
    body: 'Auto-synced from your code and BUDs, semantically searchable, and fed straight into every agent prompt.',
    to: '/platform',
  },
]

export interface Proof {
  icon: string
  label: string
}

export const SOCIAL_PROOF: Proof[] = [
  { icon: 'mdi-scale-balance', label: 'Apache 2.0' },
  { icon: 'mdi-server-security', label: 'Self-hosted — data stays local' },
  { icon: 'mdi-robot-outline', label: 'Runs on Claude Code' },
  { icon: 'mdi-github', label: 'Open source' },
]

export interface TeaserRow {
  phase: string
  agile: string
  bodhiorchard: string
}

export const VS_AGILE_TEASER: TeaserRow[] = [
  { phase: 'Estimation', agile: 'Story points, planning poker', bodhiorchard: 'AI-PERT + Monte Carlo confidence dates' },
  { phase: 'Specification', agile: 'PM writes the spec by hand', bodhiorchard: 'BUD Agent drafts it with codebase context' },
  { phase: 'Knowledge', agile: 'Confluence pages go stale', bodhiorchard: 'Auto-synced from code, always current' },
]
