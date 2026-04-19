// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

export interface AgentInfo {
  name: string
  icon: string
  triggerType: string
  triggerIcon: string
  tagline: string
  description?: string
  capabilities: string[]
  interactsWith: string[]
  color: string
}

export const agents: AgentInfo[] = [
  // Intake & Planning
  {
    name: 'Triage Agent',
    icon: 'mdi-message-flash-outline',
    triggerType: 'Chat / Slack Event',
    triggerIcon: 'mdi-lightning-bolt-outline',
    tagline: 'Interviews users, checks capacity, finds duplicates, estimates complexity, suggests priority.',
    description: 'Interviews the user with a structured intake, checks team capacity via the Capacity Service, searches for duplicates using vector search, estimates complexity from codebase analysis, and suggests priority with reassignment recommendations.',
    capabilities: [
      'Intake interview',
      'Duplicate detection',
      'Priority scoring',
      'Complexity estimation',
    ],
    interactsWith: ['BUD Agent', 'Skill Agent'],
    color: 'primary',
  },
  {
    name: 'BUD Agent',
    icon: 'mdi-file-document-edit-outline',
    triggerType: 'PM Trigger',
    triggerIcon: 'mdi-play-circle-outline',
    tagline: 'Codebase-aware spec generation with enterprise rules, prior art, and competitor analysis.',
    description: 'Generates the full BUD with deep codebase knowledge — searches enterprise rules, prior art, and competitor analysis. Outputs spec, tech spec, test plan, and acceptance criteria as a single source of truth.',
    capabilities: [
      'Codebase context',
      'Enterprise rules',
      'Competitor analysis',
      'Tech spec + tests',
    ],
    interactsWith: ['Triage Agent', 'Learning Agent'],
    color: 'secondary',
  },
  // Design & Tech Planning
  {
    name: 'Design Agent',
    icon: 'mdi-palette-outline',
    triggerType: 'BUD Approved',
    triggerIcon: 'mdi-check-circle-outline',
    tagline: 'Generates visual HTML wireframes using your project\'s extracted design system.',
    description: 'Reads the BUD requirements and your org\'s design system (extracted from '
      + 'vuetify.ts, SCSS, and package.json). Produces standalone HTML wireframes that use '
      + 'Vuetify CDN with your actual theme colors, typography, and component defaults. '
      + 'Designers can open the wireframe in any browser, iterate via AI chat, and hand '
      + 'off to frontend development.',
    capabilities: [
      'HTML wireframes',
      'Design system aware',
      'UX considerations',
      'Accessibility',
    ],
    interactsWith: ['BUD Agent', 'Tech Plan Agent'],
    color: 'secondary',
  },
  {
    name: 'Tech Plan Agent',
    icon: 'mdi-clipboard-list-outline',
    triggerType: 'BUD Approved',
    triggerIcon: 'mdi-check-circle-outline',
    tagline: 'Generates detailed technical implementation plans with file-level TODOs from approved BUDs.',
    capabilities: ['Architecture analysis', 'File-level TODOs', 'Dependency mapping', 'API contracts'],
    interactsWith: ['BUD Agent', 'Design Agent'],
    color: 'info',
  },
  // Development & Tracking
  {
    name: 'Status Agent',
    icon: 'mdi-source-branch-check',
    triggerType: 'GitHub Webhook',
    triggerIcon: 'mdi-webhook',
    tagline: 'Detects PR merges, infers status from branches, moves BUD folders, notifies stakeholders.',
    description: 'Detects PR merges via GitHub webhooks, determines status from target branch, moves BUD folders from active/ to deployed/, and notifies stakeholders automatically.',
    capabilities: [
      'PR merge detection',
      'Branch status inference',
      'Folder management',
      'Notifications',
    ],
    interactsWith: ['Learning Agent', 'Bug Linker Agent'],
    color: 'success',
  },
  {
    name: 'Standup Agent',
    icon: 'mdi-calendar-clock-outline',
    triggerType: 'Daily Cron 08:30',
    triggerIcon: 'mdi-clock-outline',
    tagline: 'Aggregates git/PR/bug/chat activity into daily summaries with risk flag detection.',
    description: 'Aggregates git commits, PR activity, bug reports, and chat messages into a daily standup summary. Detects risk flags like lagging BUDs, developer inactivity, and scope changes.',
    capabilities: [
      'Activity aggregation',
      'Risk flags',
      'Lagging BUD alerts',
      'Scope tracking',
    ],
    interactsWith: ['Status Agent', 'Bug Linker Agent'],
    color: 'warning',
  },
  // Testing & Quality
  {
    name: 'Test Plan Agent',
    icon: 'mdi-test-tube',
    triggerType: 'Dev Complete',
    triggerIcon: 'mdi-check-decagram-outline',
    tagline: 'Auto-generates test automation and manual test cases from BUD acceptance criteria and code.',
    capabilities: ['Playwright e2e', 'Unit/integration tests', 'Manual UAT cases', 'Security tests'],
    interactsWith: ['BUD Agent', 'Bug Linker Agent'],
    color: 'warning',
  },
  {
    name: 'Bug Linker Agent',
    icon: 'mdi-bug-check-outline',
    triggerType: 'New Bug Filed',
    triggerIcon: 'mdi-alert-circle-outline',
    tagline: 'Links bugs to BUDs via vector search, monitors thresholds, triggers reassignment.',
    description: 'Links newly filed bugs to their originating BUDs via vector search. Monitors a configurable threshold (complexity score x multiplier) and triggers the Reassignment Agent when exceeded.',
    capabilities: [
      'Bug-BUD linking',
      'Threshold monitor',
      'Auto-reassign trigger',
      'Classification',
    ],
    interactsWith: ['Reassignment Agent', 'Status Agent'],
    color: 'error',
  },
  {
    name: 'Reassignment Agent',
    icon: 'mdi-account-switch-outline',
    triggerType: 'Bug Linker Trigger',
    triggerIcon: 'mdi-cog-outline',
    tagline: 'Reassigns devs to bug review, rotates QA to next BUD, rebalances workloads.',
    description: 'Triggered by the Bug Linker Agent when bug thresholds are exceeded. Reassigns the original developer to bug review and moves QA to the next waiting BUD. Notifies the team of all changes.',
    capabilities: [
      'Dev reassignment',
      'QA rotation',
      'Team notification',
      'Workload balance',
    ],
    interactsWith: ['Bug Linker Agent', 'Skill Agent'],
    color: 'secondary',
  },
  // Post-Deploy & Continuous
  {
    name: 'Learning Agent',
    icon: 'mdi-brain',
    triggerType: 'BUD Deployed',
    triggerIcon: 'mdi-rocket-launch-outline',
    tagline: 'Cycle time analysis, estimate vs actual comparison, pattern matching, retrospective generation.',
    description: 'Runs after every deployment — calculates cycle time, compares estimates vs actuals, finds patterns across similar features, generates retrospectives, and embeds all learnings in the vector DB.',
    capabilities: [
      'Cycle time analysis',
      'Estimate accuracy',
      'Pattern matching',
      'Retrospectives',
    ],
    interactsWith: ['Skill Agent', 'BUD Agent', 'Triage Agent'],
    color: 'primary',
  },
  {
    name: 'Smart Assignment Agent',
    icon: 'mdi-account-arrow-right-outline',
    triggerType: 'Phase Gate Approved',
    triggerIcon: 'mdi-check-circle-outline',
    tagline: 'Assigns the best-fit developer based on skill scores, capacity, and module expertise.',
    capabilities: ['Skill matching', 'Capacity balancing', 'Module expertise', 'Workload optimization'],
    interactsWith: ['Skill Agent', 'Tech Plan Agent'],
    color: 'info',
  },
  {
    name: 'Skill Agent',
    icon: 'mdi-account-cog-outline',
    triggerType: 'Daily Cron 02:00',
    triggerIcon: 'mdi-clock-outline',
    tagline: 'Rebuilds skill profiles from git/BUD/bug history, scores 0\u20131.0, detects bus factor risks.',
    description: 'Rebuilds developer skill profiles daily from git history, BUD assignments, and bug fix records. Generates skill scores (0\u20131.0) per module, detects bus factor risks, and recommends optimal developer assignments.',
    capabilities: [
      'Profile rebuilds',
      'Skill scores',
      'Bus factor alerts',
      'Recommendations',
    ],
    interactsWith: ['Triage Agent', 'Learning Agent', 'Reassignment Agent'],
    color: 'info',
  },
]
