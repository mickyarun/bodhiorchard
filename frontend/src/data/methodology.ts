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

// Single source of truth for the methodology / marketing content. Consumed by
// the in-app /methodology route AND the public landing site, so the copy never
// drifts between the two. Sections live in components/methodology/sections/*.

export interface DemoVideo {
  value: string
  title: string
  youTubeId: string
  caption: string
}

export interface Shot {
  src: string
  alt: string
}

export interface Principle {
  value: string
  over: string
  icon: string
}

export interface ComparisonRow {
  phase: string
  agile: string
  bodhiorchard: string
}

export interface Phase {
  name: string
  icon: string
  description: string
  ai: string
  human: string
}

export interface LabeledItem {
  icon: string
  label: string
  detail: string
}

export interface KnowledgeLayer {
  num: number
  name: string
  detail: string
}

// The hero/featured video; secondary videos are everything else.
export const HERO_VIDEO_VALUE = 'world'

export const demoVideos: DemoVideo[] = [
  {
    value: 'setup',
    title: 'Setup walkthrough',
    youTubeId: 'ot-BmKxRgRA',
    caption: 'Clone, configure, and bring the stack up locally.',
  },
  {
    value: 'slack',
    title: 'Slack triage & MCP tools',
    youTubeId: 'i8kZdcL1bME',
    caption:
      'Chat-to-BUD in Slack: the Triage Agent drafts the spec, Claude Code drives the BUD lifecycle through MCP tools.',
  },
  {
    value: 'estimation',
    title: 'Requirements & estimation',
    youTubeId: 'YBwdTes0Fno',
    caption:
      'AI-drafted requirements, AI-PERT + Monte Carlo cycle-time forecasts, and the collaborative editor with full version history.',
  },
  {
    value: 'design',
    title: 'Design phase & agent prompts',
    youTubeId: 'lV71qhmfzzw',
    caption:
      'Generating wireframes and the tech architecture — and how the AI agent prompts shape each handoff.',
  },
  {
    value: 'dev',
    title: 'Development & retrospective',
    youTubeId: 'YjRihN_SKaw',
    caption:
      'Development, automated code review, post-deploy retrospective, and the Learning Agent feeding insights back into estimation.',
  },
  {
    value: 'world',
    title: 'Inside the virtual world',
    youTubeId: 'OxoqBI7BNxU',
    caption: 'The Living Tree: your org as a tended orchard.',
  },
]

export const platformShots: Shot[] = [
  { src: '/landing/livingtree.png', alt: 'Living Tree dashboard — 3D visualisation of your repos' },
  { src: '/landing/board.png', alt: 'BUD board — backlog and lifecycle view' },
  { src: '/landing/Feature.png', alt: 'Feature registry — BUDs that graduated to shipped features' },
]

export const gamificationShots: Shot[] = [
  { src: '/landing/skills.png', alt: 'Developer skill profile — module-by-module scoring' },
  { src: '/landing/gamification.png', alt: 'XP and progression' },
  { src: '/landing/LeaderBoard.png', alt: 'Leaderboard — ranked by shipped value' },
  { src: '/landing/unlocks.png', alt: 'Unlocks — badges earned through contribution patterns' },
]

export const principles: Principle[] = [
  { value: 'AI-generated first drafts', over: 'blank-page paralysis', icon: 'mdi-file-edit-outline' },
  { value: 'Cycle time predictions', over: 'story points & planning poker', icon: 'mdi-chart-timeline-variant' },
  { value: 'Continuous learning', over: 'post-mortems after the damage', icon: 'mdi-brain' },
  { value: 'Human decisions', over: 'human busywork', icon: 'mdi-account-check-outline' },
  { value: 'Living knowledge', over: 'stale Confluence pages', icon: 'mdi-database-sync-outline' },
  { value: 'BUD as single source of truth', over: 'scattered tickets & docs', icon: 'mdi-file-document-check-outline' },
  { value: 'Skills that grow with the team', over: 'static role assignments', icon: 'mdi-trending-up' },
  { value: 'Auto-healing quality loops', over: 'manual bug triage', icon: 'mdi-shield-refresh-outline' },
]

export const comparisonRows: ComparisonRow[] = [
  { phase: 'Intake', agile: 'Ticket in Jira, manual triage, sprint planning', bodhiorchard: 'Chat message → Triage Agent analyzes, finds duplicates, estimates capacity' },
  { phase: 'Estimation', agile: 'Story points, planning poker, team debate', bodhiorchard: 'AI-PERT + Monte Carlo simulation — per-phase dates with P50/P70/P85 confidence, factoring developer skill profiles, backlog depth, and workload' },
  { phase: 'Specification', agile: 'PM writes BUD manually, reviews in meetings', bodhiorchard: 'BUD Agent drafts spec with codebase context, enterprise rules, prior art' },
  { phase: 'Design', agile: 'Designer creates in Figma, hands off specs', bodhiorchard: 'AI generates wireframes; Designer reviews, edits, and advances to Tech Architecture' },
  { phase: 'Tech Arch', agile: 'Architect writes design doc, reviews in meetings', bodhiorchard: 'AI generates tech plan; Tech Lead reviews; Smart Assignment Agent suggests developer' },
  { phase: 'Development', agile: 'Dev picks up ticket, starts from scratch', bodhiorchard: 'Best-fit dev assigned by AI, implements from tech plan, human reviews code' },
  { phase: 'Testing', agile: 'QA writes test cases manually, runs regression', bodhiorchard: 'Auto-generated test plan (unit, integration, e2e, perf, security, UAT)' },
  { phase: 'QA & UAT', agile: 'QA writes test cases, manual handoff', bodhiorchard: 'QA approves/refines automation plan, executes manual tests, signs off for UAT' },
  { phase: 'Deployment', agile: 'Release train, manual status updates', bodhiorchard: 'Status Agent auto-detects PR merges, BUD becomes Feature on deploy' },
  { phase: 'Bug Mgmt', agile: 'Manual triage, reassign in standup', bodhiorchard: 'External bugs reopen Features, auto-classify and restart flow from triage' },
  { phase: 'Knowledge', agile: 'Confluence pages go stale, tribal knowledge', bodhiorchard: 'Learning Agent captures patterns, knowledge auto-syncs from code' },
  { phase: 'Skills', agile: 'Manager intuition, annual reviews', bodhiorchard: 'Skill Agent rebuilds daily from git/BUD/bug history, recommends assignments' },
  { phase: 'Retrospective', agile: 'Biweekly meeting, action items forgotten', bodhiorchard: 'Learning Agent auto-generates retrospective on every deployment' },
]

export const phases: Phase[] = [
  {
    name: 'Phase 1: Chat Intake',
    icon: 'mdi-chat-outline',
    description: 'Any chat interface (Slack, Teams, or API) receives the request. The Triage Agent analyzes it, searches for duplicates via vector search, runs a structured intake interview covering business impact, customer context, timeline, and dependencies.',
    ai: 'Analyzes request, searches for duplicates, estimates complexity from code search, generates PM recommendation with priority scoring.',
    human: 'Submits idea, answers intake questions. PM or org owner reviews triage output, modifies, and moves to BUD generation.',
  },
  {
    name: 'Phase 2: BUD Generation',
    icon: 'mdi-file-document-edit-outline',
    description: 'The BUD becomes the single source of truth — containing spec, tech spec, test plan, and acceptance criteria. The BUD Agent searches enterprise rules and prior art to auto-generate all sections. The assigned PM then reviews, refines, and advances to Design when satisfied.',
    ai: 'Searches enterprise rules & prior art, generates overview, goals, user stories, requirements, acceptance criteria, out of scope, dependencies, risks. Creates BUD folder in repo.',
    human: 'Reviews AI-generated spec, refines requirements, advances to Design when ready.',
  },
  {
    name: 'Phase 3: Design',
    icon: 'mdi-palette-outline',
    description: 'After BUD advances to Design, agents scope design requirements and generate wireframes. The assigned Designer reviews, edits in preferred tools, and advances to Tech Architecture when satisfied.',
    ai: 'Scopes design requirements, generates HTML wireframes using project design system, provides pattern recommendations, captures Figma review via MCP.',
    human: 'Reviews AI-generated wireframes, edits in preferred tools, advances to Tech Architecture when ready.',
  },
  {
    name: 'Phase 4: Tech Architecture & Development',
    icon: 'mdi-code-braces',
    description: 'After Design advances, the Tech Arch Agent generates the implementation plan. The Tech Lead reviews and advances to development. The Smart Assignment Agent suggests the best-fit developer based on skills and capacity. The Manager reviews the assignment if present, otherwise the developer is assigned directly. AI then implements with full codebase access.',
    ai: 'Generates tech plan, suggests best-fit developer via Smart Assignment Agent, implements feature following org standards.',
    human: 'Reviews tech plan, advances to development. Manager reviews developer assignment if present.',
  },
  {
    name: 'Phase 5: Auto Test Generation',
    icon: 'mdi-test-tube',
    description: 'After development, AI auto-generates a comprehensive test plan: automation tests (unit, integration, e2e, performance, security) and manual test cases (UAT scenarios, edge cases, exploratory test guides). All linked to BUD acceptance criteria.',
    ai: 'Generates unit, integration, e2e, performance, and security tests. Creates manual UAT scenarios and exploratory test guides.',
    human: 'Reviews test plan, adds domain-specific edge cases.',
  },
  {
    name: 'Phase 6: QA Takeover',
    icon: 'mdi-clipboard-check-outline',
    description: 'QA takes over the BUD. They review and approve the auto-generated test automation plan (or refine it). Then QA executes manual test cases, marks proof of completion, and signs off. Once QA approves, the BUD moves to UAT.',
    ai: 'Presents the automation plan for QA review, tracks manual test execution progress, collects proof artifacts.',
    human: 'Approves or refines the automation plan, executes manual test cases, marks proof, signs off for UAT.',
  },
  {
    name: 'Phase 7: UAT & Deployment',
    icon: 'mdi-rocket-launch-outline',
    description: 'After QA sign-off, the BUD moves through UAT validation and production deployment. The Status Agent auto-detects PR merges and determines status from target branch. Stakeholders are notified automatically.',
    ai: 'Detects PR merges, updates BUD status, notifies stakeholders, tracks deployment status.',
    human: 'Validates in UAT environment, gives go/no-go for production deployment.',
  },
  {
    name: 'Phase 8: BUD Becomes Feature',
    icon: 'mdi-star-shooting-outline',
    description: 'Once deployed to production, the BUD graduates to a Feature. It moves from the active BUD board to the feature registry — a permanent record of what was built, why, and how. The BUD lifecycle is complete.',
    ai: 'Archives BUD as a Feature in the registry, updates knowledge base, triggers learning pipeline.',
    human: 'Confirms successful deployment, validates in production.',
  },
  {
    name: 'Phase 9: Learning & Skill Growth',
    icon: 'mdi-brain',
    description: 'The Learning Agent calculates cycle time, compares estimates vs actual, finds patterns across similar features, generates retrospective, and embeds learnings in vector DB. The Skill Agent rebuilds dev profiles daily.',
    ai: 'Calculates cycle time, generates retrospective, detects bus factor alerts, recommends future assignments based on expertise + capacity. Knowledge auto-syncs: code → CLAUDE.md → PostgreSQL → vector search.',
    human: 'Reviews insights, validates learnings, curates enterprise rules.',
  },
  {
    name: 'Bug Reopening',
    icon: 'mdi-bug-outline',
    description: 'Bugs originate externally — from production monitoring, user reports, or support tickets. When a bug is linked to an existing Feature, it reopens that Feature and restarts the flow from triage. The bug is classified and the cycle begins again.',
    ai: 'Links bugs to Features via vector search, auto-classifies as "missed requirement" vs "implementation bug", reopens the Feature, triggers triage.',
    human: 'Reports the bug, validates classification, prioritizes the fix.',
  },
]

export const aiHandles: string[] = [
  'Intake analysis & duplicate detection',
  'BUD drafting with codebase context',
  'Design scope & tech plan generation',
  'Test case generation (automation + manual)',
  'Bug-to-BUD linking & threshold monitoring',
  'Status tracking & stakeholder updates',
  'Pattern recognition & retrospectives',
  'Skill profiling & assignment recommendations',
  'Knowledge sync (code → docs → vector DB)',
  'AI-PERT estimation with Monte Carlo confidence intervals',
  'Smart developer assignment based on skills & capacity',
]

export const humanHandles: string[] = [
  'Review and advance decisions at every phase',
  'Code review & architecture choices',
  'Visual design in preferred tools',
  'Business trade-offs & prioritization',
  'Quality validation & UAT sign-off',
  'Reassignment review & override',
  'Knowledge curation & enterprise rules',
]

export const qualityLoopItems: LabeledItem[] = [
  { icon: 'mdi-gauge', label: 'Bug Threshold', detail: 'complexity × multiplier — configurable per org. When exceeded, auto-reassignment triggers.' },
  { icon: 'mdi-swap-horizontal', label: 'Auto-Reassignment', detail: 'Original dev moves to bug review, QA moves to next waiting BUD.' },
  { icon: 'mdi-file-restore-outline', label: 'Feature Reopening', detail: 'External bugs reopen the Feature and restart the flow from triage.' },
  { icon: 'mdi-tag-outline', label: 'Auto-Classification', detail: 'Each bug classified as "missed feature" vs "development bug" — drives different fix paths.' },
  { icon: 'mdi-lightbulb-on-outline', label: 'Knowledge Capture', detail: 'Every bug fix adds to the knowledge base — prevents the same bug class from recurring.' },
]

export const backlogItems: LabeledItem[] = [
  { icon: 'mdi-sort-variant', label: 'Capacity-Aware Triage', detail: 'Triage Agent deprioritizes or defers items based on real-time team capacity.' },
  { icon: 'mdi-shuffle-variant', label: 'Dynamic Reassignment', detail: 'Reassignment Agent shuffles work based on shifting business demand.' },
  { icon: 'mdi-star-outline', label: 'Customer Priority Scoring', detail: 'ARR + severity + tier drives backlog ordering automatically.' },
  { icon: 'mdi-account-star-outline', label: 'Best-Fit Developer', detail: 'Skill Agent recommends the best-fit developer for each backlog item.' },
  { icon: 'mdi-chart-timeline-variant', label: 'Real-Time Utilization', detail: 'Per-developer capacity tracking ensures balanced workloads.' },
]

export const knowledgeLayers: KnowledgeLayer[] = [
  { num: 1, name: 'Git Repos', detail: 'Source code + per-repo CLAUDE.md (syncs every 15 min)' },
  { num: 2, name: 'Agent Skills', detail: 'Org standards, design guidelines, API patterns (syncs on change)' },
  { num: 3, name: 'Central DB', detail: 'BUDs, enterprise rules, architecture decisions (real-time)' },
  { num: 4, name: 'Vector Search', detail: 'Semantic search across everything (auto-indexed)' },
]

export const knowledgeAdvantages: string[] = [
  'Auto-synced from source — not manually maintained',
  'Semantically searchable — not keyword search',
  'Always current — daily staleness detection',
  'Integrated into agent prompts — agents always have latest context',
]

export const skillItems: LabeledItem[] = [
  { icon: 'mdi-history', label: 'Daily Profile Rebuilds', detail: 'Analyzes git history, BUD assignments, and bug fixes to build skill scores (0–1.0) per module.' },
  { icon: 'mdi-alert-outline', label: 'Bus Factor Alerts', detail: 'Detects modules touched by only one person — flags knowledge concentration risk.' },
  { icon: 'mdi-account-arrow-right-outline', label: 'Assignment Recommendations', detail: 'Recommends developers for new BUDs based on expertise match + available capacity.' },
  { icon: 'mdi-trending-up', label: 'Evolving Skills', detail: 'Skills grow automatically as developers contribute — no manual profile updates needed.' },
]

export const budStatuses: string[] = ['bud', 'design', 'tech_arch', 'development', 'testing', 'uat', 'prod', 'closed']

export const budFeatures: string[] = [
  'Contains spec, tech spec, test plan, acceptance criteria, and metadata',
  'Any stage can return to BUD (e.g., post-deployment bugs)',
  'Bug classification on reopen: "missed feature" vs "development bug"',
  'Full history tracked: stage transitions, assignees, reopens, bugs',
  'Vector-indexed for semantic search by all agents',
]
