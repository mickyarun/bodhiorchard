<template>
  <div class="methodology-page">
    <!-- Section 1: Header -->
    <div class="d-flex flex-column align-center text-center mb-10">
      <v-icon
        icon="mdi-book-open-page-variant-outline"
        size="48"
        color="secondary"
        class="mb-4"
      />
      <h1 class="text-h4 font-weight-bold mb-2">
        The Bodhigrove Methodology
      </h1>
      <p class="text-body-1 text-medium-emphasis mb-5" style="max-width: 600px;">
        An AI-first alternative to Agile. From chat to deployment — every phase powered by intelligent agents.
      </p>
      <v-btn
        color="primary"
        variant="outlined"
        append-icon="mdi-arrow-right"
        @click="emit('startBuilding')"
      >
        Start Building
      </v-btn>
    </div>

    <!-- Section 2: The Flow (Lifecycle Flowchart) -->
    <div class="mb-8">
      <div class="text-h6 font-weight-medium mb-4 text-center">The Flow</div>
      <LifecycleFlowchart class="mb-6" />

      <v-expansion-panels class="phase-expansion-panels" variant="accordion">
        <v-expansion-panel v-for="phase in phases" :key="phase.name">
          <v-expansion-panel-title>
            <div class="d-flex align-center ga-3">
              <v-icon :icon="phase.icon" size="20" color="primary" />
              <span class="font-weight-medium">{{ phase.name }}</span>
            </div>
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <p class="text-body-2 text-medium-emphasis mb-3">{{ phase.description }}</p>
            <v-row dense>
              <v-col cols="12" sm="6">
                <div class="d-flex align-center mb-2">
                  <v-icon icon="mdi-robot-outline" size="16" color="primary" class="mr-1" />
                  <span class="text-caption font-weight-medium">AI Role</span>
                </div>
                <div class="text-body-2 text-medium-emphasis">{{ phase.ai }}</div>
              </v-col>
              <v-col cols="12" sm="6">
                <div class="d-flex align-center mb-2">
                  <v-icon icon="mdi-account-outline" size="16" color="secondary" class="mr-1" />
                  <span class="text-caption font-weight-medium">Human Role</span>
                </div>
                <div class="text-body-2 text-medium-emphasis">{{ phase.human }}</div>
              </v-col>
            </v-row>
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </div>

    <!-- Section 3: Core Principles (Manifesto) — 2-column grid -->
    <v-card class="pa-6 mb-8 card-border-dark" color="surface">
      <div class="text-overline text-medium-emphasis mb-4">Our Manifesto</div>
      <v-row dense>
        <v-col
          v-for="(principle, index) in principles"
          :key="index"
          cols="12"
          sm="6"
        >
          <div
            class="methodology-principle"
            :class="index % 2 === 0 ? 'border-primary' : 'border-secondary'"
          >
            <v-icon
              :icon="principle.icon"
              size="16"
              :color="index % 2 === 0 ? 'primary' : 'secondary'"
              class="mr-2 flex-shrink-0"
            />
            <span class="text-body-2">
              <strong :class="index % 2 === 0 ? 'text-primary' : 'text-secondary'">{{ principle.value }}</strong>
              <span class="text-medium-emphasis"> over {{ principle.over }}</span>
            </span>
          </div>
        </v-col>
      </v-row>
    </v-card>

    <!-- Section 4: Meet the Agents -->
    <div class="mb-8">
      <div class="d-flex flex-column align-center text-center mb-5">
        <v-icon icon="mdi-robot-happy-outline" size="32" color="primary" class="mb-2" />
        <div class="text-h6 font-weight-medium">Meet the Agents</div>
        <p class="text-caption text-medium-emphasis" style="max-width: 480px;">
          Eleven specialized agents orchestrate every phase — triggered automatically, connected to each other.
        </p>
      </div>
      <v-row dense>
        <v-col
          v-for="agent in agents"
          :key="agent.name"
          cols="12"
          sm="6"
          lg="3"
        >
          <AgentCard :agent="agent" />
        </v-col>
      </v-row>
    </div>

    <!-- Section 6: Human + AI Loop — side by side -->
    <v-row class="mb-8" justify="center">
      <v-col cols="12" sm="6">
        <v-card class="pa-5 card-border-dark h-100" color="surface">
          <div class="d-flex align-center mb-3">
            <v-icon icon="mdi-robot-outline" color="primary" class="mr-2" />
            <div class="text-subtitle-1 font-weight-medium">AI Handles</div>
          </div>
          <div class="d-flex flex-column ga-2">
            <div v-for="item in aiHandles" :key="item" class="text-body-2 text-medium-emphasis">
              <v-icon icon="mdi-check" size="14" color="primary" class="mr-1" />
              {{ item }}
            </div>
          </div>
        </v-card>
      </v-col>
      <v-col cols="12" sm="6">
        <v-card class="pa-5 card-border-dark h-100" color="surface">
          <div class="d-flex align-center mb-3">
            <v-icon icon="mdi-account-outline" color="secondary" class="mr-2" />
            <div class="text-subtitle-1 font-weight-medium">Humans Handle</div>
          </div>
          <div class="d-flex flex-column ga-2">
            <div v-for="item in humanHandles" :key="item" class="text-body-2 text-medium-emphasis">
              <v-icon icon="mdi-check" size="14" color="secondary" class="mr-1" />
              {{ item }}
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Section 7: Cycle Time + BUD— side by side -->
    <v-row class="mb-8">
      <v-col cols="12" md="6">
        <v-card class="pa-5 card-border-dark h-100" color="surface">
          <div class="d-flex align-center mb-3">
            <v-icon icon="mdi-chart-timeline-variant-shimmer" color="primary" class="mr-2" />
            <div class="text-subtitle-1 font-weight-medium">AI-Predicted Cycle Time</div>
          </div>
          <div class="text-body-2 text-medium-emphasis mb-3">
            <span class="text-decoration-line-through text-error mr-1">Story points</span>
            <span class="text-decoration-line-through text-error mr-1">Planning poker</span>
            — replaced by data-driven predictions.
          </div>
          <p class="text-body-2 text-medium-emphasis mb-3">
            The Learning Agent analyzes completed features — complexity, code changes, review cycles,
            similar past features — to predict how long new work will take.
          </p>
          <v-card variant="outlined" class="pa-3 mb-3" color="surface-variant">
            <div class="text-caption text-medium-emphasis mb-1">Example Prediction</div>
            <div class="text-body-2">
              <strong>Feature:</strong> User Settings Page
            </div>
            <div class="text-body-2 text-medium-emphasis">
              Predicted: 3–5 days (based on 4 similar UI features, team expertise: 0.92)
            </div>
          </v-card>
          <div class="d-flex flex-wrap ga-2">
            <v-chip color="primary" variant="tonal" size="small">Expected: 2–4 days</v-chip>
            <v-chip color="secondary" variant="tonal" size="small">Confidence: 85%</v-chip>
            <v-chip color="success" variant="tonal" size="small">Based on 3 similar features</v-chip>
          </div>
        </v-card>
      </v-col>
      <v-col cols="12" md="6">
        <v-card class="pa-5 card-border-dark h-100" color="surface">
          <div class="d-flex align-center mb-3">
            <v-icon icon="mdi-file-document-check-outline" color="primary" class="mr-2" />
            <div class="text-subtitle-1 font-weight-medium">BUD: Single Source of Truth</div>
          </div>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Every feature lives in one BUD— spec, tech spec, test plan, acceptance criteria, and full history.
            Replaces scattered Jira tickets, Google Docs, and Notion pages.
          </p>
          <div class="d-flex flex-wrap ga-2 mb-4">
            <v-chip
              v-for="status in budStatuses"
              :key="status"
              variant="tonal"
              size="small"
              :color="status === 'deployed' ? 'success' : 'primary'"
            >
              {{ status }}
            </v-chip>
          </div>
          <div class="d-flex flex-column ga-2">
            <div v-for="item in budFeatures" :key="item" class="text-body-2 text-medium-emphasis">
              <v-icon icon="mdi-check" size="14" color="primary" class="mr-1" />
              {{ item }}
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Section 8: Quality Loops + Backlog — side by side -->
    <v-row class="mb-8">
      <v-col cols="12" md="6">
        <v-card class="pa-5 card-border-dark h-100" color="surface">
          <div class="d-flex align-center mb-3">
            <v-icon icon="mdi-shield-refresh-outline" color="primary" class="mr-2" />
            <div class="text-subtitle-1 font-weight-medium">Smart Quality Loops</div>
          </div>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Auto-healing bug management that prevents quality debt from accumulating.
          </p>
          <div class="d-flex flex-column ga-3">
            <div v-for="item in qualityLoopItems" :key="item.label" class="d-flex align-start ga-2">
              <v-icon :icon="item.icon" size="18" color="primary" class="mt-1 flex-shrink-0" />
              <div>
                <div class="text-body-2 font-weight-medium">{{ item.label }}</div>
                <div class="text-caption text-medium-emphasis">{{ item.detail }}</div>
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
      <v-col cols="12" md="6">
        <v-card class="pa-5 card-border-dark h-100" color="surface">
          <div class="d-flex align-center mb-3">
            <v-icon icon="mdi-format-list-checks" color="secondary" class="mr-2" />
            <div class="text-subtitle-1 font-weight-medium">Backlog Intelligence</div>
          </div>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Smart backlog management driven by data, not gut feelings.
          </p>
          <div class="d-flex flex-column ga-3">
            <div v-for="item in backlogItems" :key="item.label" class="d-flex align-start ga-2">
              <v-icon :icon="item.icon" size="18" color="secondary" class="mt-1 flex-shrink-0" />
              <div>
                <div class="text-body-2 font-weight-medium">{{ item.label }}</div>
                <div class="text-caption text-medium-emphasis">{{ item.detail }}</div>
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Section 9: Knowledge + Skills — side by side -->
    <v-row class="mb-8">
      <v-col cols="12" md="6">
        <v-card class="pa-5 card-border-dark h-100" color="surface">
          <div class="d-flex align-center mb-3">
            <v-icon icon="mdi-database-sync-outline" color="primary" class="mr-2" />
            <div class="text-subtitle-1 font-weight-medium">Knowledge That Grows</div>
          </div>
          <p class="text-body-2 text-medium-emphasis mb-4">
            A 4-layer knowledge architecture that replaces stale wikis with living, auto-synced knowledge.
          </p>
          <div class="d-flex flex-column ga-2 mb-4">
            <div
              v-for="layer in knowledgeLayers"
              :key="layer.name"
              class="methodology-knowledge-layer"
            >
              <div class="layer-number">{{ layer.num }}</div>
              <div>
                <div class="text-body-2 font-weight-medium">{{ layer.name }}</div>
                <div class="text-caption text-medium-emphasis">{{ layer.detail }}</div>
              </div>
            </div>
          </div>
          <div class="text-overline text-medium-emphasis mb-2">Why This Beats Confluence</div>
          <div class="d-flex flex-column ga-1">
            <div v-for="adv in knowledgeAdvantages" :key="adv" class="text-caption text-medium-emphasis">
              <v-icon icon="mdi-check-circle-outline" size="12" color="success" class="mr-1" />
              {{ adv }}
            </div>
          </div>
        </v-card>
      </v-col>
      <v-col cols="12" md="6">
        <v-card class="pa-5 card-border-dark h-100" color="surface">
          <div class="d-flex align-center mb-3">
            <v-icon icon="mdi-account-cog-outline" color="secondary" class="mr-2" />
            <div class="text-subtitle-1 font-weight-medium">Dev Skill Maintenance</div>
          </div>
          <p class="text-body-2 text-medium-emphasis mb-4">
            The Skill Agent rebuilds developer profiles daily — no manual updates, no stale resumes.
          </p>
          <div class="d-flex flex-column ga-3">
            <div v-for="item in skillItems" :key="item.label" class="d-flex align-start ga-2">
              <v-icon :icon="item.icon" size="18" color="secondary" class="mt-1 flex-shrink-0" />
              <div>
                <div class="text-body-2 font-weight-medium">{{ item.label }}</div>
                <div class="text-caption text-medium-emphasis">{{ item.detail }}</div>
              </div>
            </div>
          </div>
        </v-card>
      </v-col>
    </v-row>

    <!-- Section 10: Bodhigrove vs Agile (comparison) -->
    <v-card class="pa-6 mb-8 card-border-dark" color="surface">
      <div class="text-overline text-medium-emphasis mb-4">Bodhigrove vs Agile</div>
      <div style="overflow-x: auto;">
        <table class="methodology-comparison">
          <thead>
            <tr>
              <th>Phase</th>
              <th>Agile / Scrum</th>
              <th>Bodhigrove</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in comparisonRows" :key="row.phase">
              <td>{{ row.phase }}</td>
              <td>{{ row.agile }}</td>
              <td>{{ row.bodhigrove }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </v-card>

    <!-- Section 11: Why Bodhigrove -->
    <v-card class="pa-8 mb-8 card-border-dark" color="surface">
      <div class="d-flex flex-column align-center text-center mb-6">
        <v-icon icon="mdi-tree-outline" size="40" color="success" class="mb-3" />
        <div class="text-h6 font-weight-medium">Why "Bodhigrove"?</div>
      </div>

      <div class="story-content mx-auto" style="max-width: 680px;">
        <p class="text-body-1 text-center font-italic text-medium-emphasis mb-6" style="line-height: 1.8;">
          "The purpose of technology is not to keep humans chained to screens, but to set them free."
        </p>

        <p class="text-body-2 text-medium-emphasis mb-4" style="line-height: 1.8;">
          <strong class="text-primary">Bodhi</strong> (Sanskrit: "awakening, enlightenment") is the state
          of understanding that the Buddha attained under the Bodhi tree.
          <strong class="text-primary">Grove</strong> is a small, living community of trees growing together.
        </p>

        <p class="text-body-2 text-medium-emphasis mb-4" style="line-height: 1.8;">
          The software industry has a paradox: we build tools to make life better,
          but the process of building them consumes our lives. Developers work late nights.
          PMs spend weekends writing specs. Teams sit through hours of ceremonies &mdash;
          standups, sprint planning, retrospectives, estimation poker &mdash; rituals
          that were meant to help but became the work itself.
        </p>

        <p class="text-body-2 text-medium-emphasis mb-4" style="line-height: 1.8;">
          Bodhigrove exists because <strong class="text-high-emphasis">AI should give humans their time back</strong>.
          Not to write more code. Not to ship faster. But to reclaim the hours lost to busywork &mdash;
          so a developer can leave at 5pm and take their kid to the park. So a PM can spend their
          morning thinking deeply about what users need instead of copy-pasting tickets. So a team
          lead can mentor junior engineers instead of chasing status updates across five tools.
        </p>

        <p class="text-body-2 text-medium-emphasis mb-4" style="line-height: 1.8;">
          The living tree dashboard isn't just a visualization &mdash; it's the philosophy made visible.
          Your organization is a grove. Each repository is a tree. Each feature is a branch.
          The AI agents are the gardeners: they water, they prune, they tend the soil. They do the
          repetitive labor so the trees can grow naturally, and the humans who planted them can step
          back, breathe, and enjoy the forest they've built.
        </p>

        <p class="text-body-2 text-medium-emphasis" style="line-height: 1.8;">
          The Bodhi tree is where awakening happened &mdash; not through more effort, but through
          stillness and clarity. Bodhigrove is an invitation to build software the same way:
          let the machines handle the noise, so humans can focus on what actually matters.
          <strong class="text-success">Build well. Then go outside.</strong>
        </p>
      </div>
    </v-card>

    <!-- Section 12: CTA -->
    <div class="d-flex justify-center">
      <v-btn
        color="primary"
        size="large"
        append-icon="mdi-arrow-right"
        @click="emit('startBuilding')"
      >
        Start Building
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import LifecycleFlowchart from '@/components/setup/LifecycleFlowchart.vue'
import AgentCard from '@/components/setup/AgentCard.vue'
import { agents } from '@/data/agents'

const emit = defineEmits<{
  startBuilding: []
}>()

const principles = [
  { value: 'AI-generated first drafts', over: 'blank-page paralysis', icon: 'mdi-file-edit-outline' },
  { value: 'Cycle time predictions', over: 'story points & planning poker', icon: 'mdi-chart-timeline-variant' },
  { value: 'Continuous learning', over: 'post-mortems after the damage', icon: 'mdi-brain' },
  { value: 'Human decisions', over: 'human busywork', icon: 'mdi-account-check-outline' },
  { value: 'Living knowledge', over: 'stale Confluence pages', icon: 'mdi-database-sync-outline' },
  { value: 'BUD as single source of truth', over: 'scattered tickets & docs', icon: 'mdi-file-document-check-outline' },
  { value: 'Skills that grow with the team', over: 'static role assignments', icon: 'mdi-trending-up' },
  { value: 'Auto-healing quality loops', over: 'manual bug triage', icon: 'mdi-shield-refresh-outline' },
]

const comparisonRows = [
  { phase: 'Intake', agile: 'Ticket in Jira, manual triage, sprint planning', bodhigrove: 'Chat message → Triage Agent analyzes, finds duplicates, estimates capacity' },
  { phase: 'Estimation', agile: 'Story points, planning poker, team debate', bodhigrove: 'AI predicts cycle time from historical features, 85% confidence' },
  { phase: 'Specification', agile: 'PM writes BUD manually, reviews in meetings', bodhigrove: 'BUD Agent drafts spec with codebase context, enterprise rules, prior art' },
  { phase: 'Design', agile: 'Designer creates in Figma, hands off specs', bodhigrove: 'Agents scope design, capture Figma review via MCP, auto-generate tech plan' },
  { phase: 'Development', agile: 'Dev picks up ticket, starts from scratch', bodhigrove: 'AI agent implements on preferred infra, dev does code review' },
  { phase: 'Testing', agile: 'QA writes test cases manually, runs regression', bodhigrove: 'Auto-generated test plan (unit, integration, e2e, perf, security, UAT)' },
  { phase: 'QA & UAT', agile: 'QA writes test cases, manual handoff', bodhigrove: 'QA approves/refines automation plan, executes manual tests, signs off for UAT' },
  { phase: 'Deployment', agile: 'Release train, manual status updates', bodhigrove: 'Status Agent auto-detects PR merges, BUD becomes Feature on deploy' },
  { phase: 'Bug Mgmt', agile: 'Manual triage, reassign in standup', bodhigrove: 'External bugs reopen Features, auto-classify and restart flow from triage' },
  { phase: 'Knowledge', agile: 'Confluence pages go stale, tribal knowledge', bodhigrove: 'Learning Agent captures patterns, knowledge auto-syncs from code' },
  { phase: 'Skills', agile: 'Manager intuition, annual reviews', bodhigrove: 'Skill Agent rebuilds daily from git/BUD/bug history, recommends assignments' },
  { phase: 'Retrospective', agile: 'Biweekly meeting, action items forgotten', bodhigrove: 'Learning Agent auto-generates retrospective on every deployment' },
]

const phases = [
  {
    name: 'Phase 1: Chat Intake',
    icon: 'mdi-chat-outline',
    description: 'Any chat interface (Slack, Teams, or API) receives the request. The Triage Agent analyzes it, searches for duplicates via vector search, runs a structured intake interview covering business impact, customer context, timeline, and dependencies.',
    ai: 'Analyzes request, searches for duplicates, estimates complexity from code search, generates PM recommendation with priority scoring.',
    human: 'Submits idea, answers intake questions, approves or deprioritizes.',
  },
  {
    name: 'Phase 2: BUD Generation',
    icon: 'mdi-file-document-edit-outline',
    description: 'The BUD becomes the single source of truth — containing spec, tech spec, test plan, and acceptance criteria. The BUD Agent searches enterprise rules and prior art to auto-generate all sections.',
    ai: 'Searches enterprise rules & prior art, generates overview, goals, user stories, requirements, acceptance criteria, out of scope, dependencies, risks. Creates BUD folder in repo.',
    human: 'Reviews, refines, and approves the BUD.',
  },
  {
    name: 'Phase 3: Design',
    icon: 'mdi-palette-outline',
    description: 'After BUD approval, agents scope design requirements. Each relevant agent provides design input (scope, constraints, patterns). MCP integration captures design review from Figma or preferred design tool.',
    ai: 'Scopes design requirements, provides pattern recommendations, captures Figma review via MCP, auto-generates technical plan from approved design.',
    human: 'Creates visual design in preferred tools, reviews agent-generated tech plan, approves for development.',
  },
  {
    name: 'Phase 4: Development',
    icon: 'mdi-code-braces',
    description: 'AI agent implements based on the approved tech plan with full codebase access — reads CLAUDE.md, org standards, and design guidelines. Works on any preferred infrastructure.',
    ai: 'Implements feature following tech plan, org standards, and design guidelines. Full codebase context.',
    human: 'Does code review, approves PRs, makes architecture decisions.',
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

const aiHandles = [
  'Intake analysis & duplicate detection',
  'BUD drafting with codebase context',
  'Design scope & tech plan generation',
  'Test case generation (automation + manual)',
  'Bug-to-BUD linking & threshold monitoring',
  'Status tracking & stakeholder updates',
  'Pattern recognition & retrospectives',
  'Skill profiling & assignment recommendations',
  'Knowledge sync (code → docs → vector DB)',
  'Capacity planning & workload balancing',
]

const humanHandles = [
  'Approval decisions at every gate',
  'Code review & architecture choices',
  'Visual design in preferred tools',
  'Business trade-offs & prioritization',
  'Quality validation & UAT sign-off',
  'Reassignment review & override',
  'Knowledge curation & enterprise rules',
]

const qualityLoopItems = [
  { icon: 'mdi-gauge', label: 'Bug Threshold', detail: 'complexity × multiplier — configurable per org. When exceeded, auto-reassignment triggers.' },
  { icon: 'mdi-swap-horizontal', label: 'Auto-Reassignment', detail: 'Original dev moves to bug review, QA moves to next waiting BUD.' },
  { icon: 'mdi-file-restore-outline', label: 'Feature Reopening', detail: 'External bugs reopen the Feature and restart the flow from triage.' },
  { icon: 'mdi-tag-outline', label: 'Auto-Classification', detail: 'Each bug classified as "missed feature" vs "development bug" — drives different fix paths.' },
  { icon: 'mdi-lightbulb-on-outline', label: 'Knowledge Capture', detail: 'Every bug fix adds to the knowledge base — prevents the same bug class from recurring.' },
]

const backlogItems = [
  { icon: 'mdi-sort-variant', label: 'Capacity-Aware Triage', detail: 'Triage Agent deprioritizes or defers items based on real-time team capacity.' },
  { icon: 'mdi-shuffle-variant', label: 'Dynamic Reassignment', detail: 'Reassignment Agent shuffles work based on shifting business demand.' },
  { icon: 'mdi-star-outline', label: 'Customer Priority Scoring', detail: 'ARR + severity + tier drives backlog ordering automatically.' },
  { icon: 'mdi-account-star-outline', label: 'Best-Fit Developer', detail: 'Skill Agent recommends the best-fit developer for each backlog item.' },
  { icon: 'mdi-chart-timeline-variant', label: 'Real-Time Utilization', detail: 'Per-developer capacity tracking ensures balanced workloads.' },
]

const knowledgeLayers = [
  { num: 1, name: 'Git Repos', detail: 'Source code + per-repo CLAUDE.md (syncs every 15 min)' },
  { num: 2, name: 'Agent Skills', detail: 'Org standards, design guidelines, API patterns (syncs on change)' },
  { num: 3, name: 'Central DB', detail: 'BUDs, enterprise rules, architecture decisions (real-time)' },
  { num: 4, name: 'Vector Search', detail: 'Semantic search across everything (auto-indexed)' },
]

const knowledgeAdvantages = [
  'Auto-synced from source — not manually maintained',
  'Semantically searchable — not keyword search',
  'Always current — daily staleness detection',
  'Integrated into agent prompts — agents always have latest context',
]

const skillItems = [
  { icon: 'mdi-history', label: 'Daily Profile Rebuilds', detail: 'Analyzes git history, BUDassignments, and bug fixes to build skill scores (0–1.0) per module.' },
  { icon: 'mdi-alert-outline', label: 'Bus Factor Alerts', detail: 'Detects modules touched by only one person — flags knowledge concentration risk.' },
  { icon: 'mdi-account-arrow-right-outline', label: 'Assignment Recommendations', detail: 'Recommends developers for new BUDs based on expertise match + available capacity.' },
  { icon: 'mdi-trending-up', label: 'Evolving Skills', detail: 'Skills grow automatically as developers contribute — no manual profile updates needed.' },
]

const budStatuses = ['bud', 'design', 'development', 'testing', 'uat', 'prod', 'closed']

const budFeatures = [
  'Contains spec, tech spec, test plan, acceptance criteria, and metadata',
  'Any stage can return to BUD (e.g., post-deployment bugs)',
  'Bug classification on reopen: "missed feature" vs "development bug"',
  'Full history tracked: stage transitions, assignees, reopens, bugs',
  'Vector-indexed for semantic search by all agents',
]
</script>
