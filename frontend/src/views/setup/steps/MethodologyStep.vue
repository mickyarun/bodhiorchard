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
        The FlowDev Methodology
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

    <!-- Section 2: Core Principles (Manifesto) — 2-column grid -->
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

    <!-- Section 3: The Flow (Lifecycle Flowchart) -->
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

    <!-- Section 7: Cycle Time + PRD — side by side -->
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
            <div class="text-subtitle-1 font-weight-medium">PRD: Single Source of Truth</div>
          </div>
          <p class="text-body-2 text-medium-emphasis mb-3">
            Every feature lives in one PRD — spec, tech spec, test plan, acceptance criteria, and full history.
            Replaces scattered Jira tickets, Google Docs, and Notion pages.
          </p>
          <div class="d-flex flex-wrap ga-2 mb-4">
            <v-chip
              v-for="status in prdStatuses"
              :key="status"
              variant="tonal"
              size="small"
              :color="status === 'deployed' ? 'success' : 'primary'"
            >
              {{ status }}
            </v-chip>
          </div>
          <div class="d-flex flex-column ga-2">
            <div v-for="item in prdFeatures" :key="item" class="text-body-2 text-medium-emphasis">
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

    <!-- Section 10: FlowDev vs Agile (comparison) -->
    <v-card class="pa-6 mb-8 card-border-dark" color="surface">
      <div class="text-overline text-medium-emphasis mb-4">FlowDev vs Agile</div>
      <div style="overflow-x: auto;">
        <table class="methodology-comparison">
          <thead>
            <tr>
              <th>Phase</th>
              <th>Agile / Scrum</th>
              <th>FlowDev</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in comparisonRows" :key="row.phase">
              <td>{{ row.phase }}</td>
              <td>{{ row.agile }}</td>
              <td>{{ row.flowdev }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </v-card>

    <!-- Section 11: CTA -->
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
import type { AgentInfo } from '@/components/setup/AgentCard.vue'

const emit = defineEmits<{
  startBuilding: []
}>()

const agents: AgentInfo[] = [
  // ── Intake & Planning ──────────────────────────────────────
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
    interactsWith: ['PRD Agent', 'Skill Agent'],
    color: 'primary',
  },
  {
    name: 'PRD Agent',
    icon: 'mdi-file-document-edit-outline',
    triggerType: 'PM Trigger',
    triggerIcon: 'mdi-play-circle-outline',
    tagline: 'Codebase-aware spec generation with enterprise rules, prior art, and competitor analysis.',
    description: 'Generates the full PRD with deep codebase knowledge — searches enterprise rules, prior art, and competitor analysis. Outputs spec, tech spec, test plan, and acceptance criteria as a single source of truth.',
    capabilities: [
      'Codebase context',
      'Enterprise rules',
      'Competitor analysis',
      'Tech spec + tests',
    ],
    interactsWith: ['Triage Agent', 'Learning Agent'],
    color: 'secondary',
  },
  // ── Design & Tech Planning ─────────────────────────────────
  {
    name: 'Design Agent',
    icon: 'mdi-palette-outline',
    triggerType: 'PRD Approved',
    triggerIcon: 'mdi-check-circle-outline',
    tagline: 'Scopes UI/UX design requirements and generates component breakdowns and interaction specs.',
    capabilities: ['Component breakdown', 'User flows', 'Interaction specs', 'Accessibility'],
    interactsWith: ['PRD Agent', 'Tech Plan Agent'],
    color: 'secondary',
  },
  {
    name: 'Tech Plan Agent',
    icon: 'mdi-clipboard-list-outline',
    triggerType: 'PRD Approved',
    triggerIcon: 'mdi-check-circle-outline',
    tagline: 'Generates detailed technical implementation plans with file-level TODOs from approved PRDs.',
    capabilities: ['Architecture analysis', 'File-level TODOs', 'Dependency mapping', 'API contracts'],
    interactsWith: ['PRD Agent', 'Design Agent'],
    color: 'info',
  },
  // ── Development & Tracking ─────────────────────────────────
  {
    name: 'Status Agent',
    icon: 'mdi-source-branch-check',
    triggerType: 'GitHub Webhook',
    triggerIcon: 'mdi-webhook',
    tagline: 'Detects PR merges, infers status from branches, moves PRD folders, notifies stakeholders.',
    description: 'Detects PR merges via GitHub webhooks, determines status from target branch, moves PRD folders from active/ to deployed/, and notifies stakeholders automatically.',
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
    description: 'Aggregates git commits, PR activity, bug reports, and chat messages into a daily standup summary. Detects risk flags like lagging PRDs, developer inactivity, and scope changes.',
    capabilities: [
      'Activity aggregation',
      'Risk flags',
      'Lagging PRD alerts',
      'Scope tracking',
    ],
    interactsWith: ['Status Agent', 'Bug Linker Agent'],
    color: 'warning',
  },
  // ── Testing & Quality ──────────────────────────────────────
  {
    name: 'Test Plan Agent',
    icon: 'mdi-test-tube',
    triggerType: 'Dev Complete',
    triggerIcon: 'mdi-check-decagram-outline',
    tagline: 'Auto-generates test automation and manual test cases from PRD acceptance criteria and code.',
    capabilities: ['Playwright e2e', 'Unit/integration tests', 'Manual UAT cases', 'Security tests'],
    interactsWith: ['PRD Agent', 'Bug Linker Agent'],
    color: 'warning',
  },
  {
    name: 'Bug Linker Agent',
    icon: 'mdi-bug-check-outline',
    triggerType: 'New Bug Filed',
    triggerIcon: 'mdi-alert-circle-outline',
    tagline: 'Links bugs to PRDs via vector search, monitors thresholds, triggers reassignment.',
    description: 'Links newly filed bugs to their originating PRDs via vector search. Monitors a configurable threshold (complexity score × multiplier) and triggers the Reassignment Agent when exceeded.',
    capabilities: [
      'Bug-PRD linking',
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
    tagline: 'Reassigns devs to bug review, rotates QA to next PRD, rebalances workloads.',
    description: 'Triggered by the Bug Linker Agent when bug thresholds are exceeded. Reassigns the original developer to bug review and moves QA to the next waiting PRD. Notifies the team of all changes.',
    capabilities: [
      'Dev reassignment',
      'QA rotation',
      'Team notification',
      'Workload balance',
    ],
    interactsWith: ['Bug Linker Agent', 'Skill Agent'],
    color: 'secondary',
  },
  // ── Post-Deploy & Continuous ───────────────────────────────
  {
    name: 'Learning Agent',
    icon: 'mdi-brain',
    triggerType: 'PRD Deployed',
    triggerIcon: 'mdi-rocket-launch-outline',
    tagline: 'Cycle time analysis, estimate vs actual comparison, pattern matching, retrospective generation.',
    description: 'Runs after every deployment — calculates cycle time, compares estimates vs actuals, finds patterns across similar features, generates retrospectives, and embeds all learnings in the vector DB.',
    capabilities: [
      'Cycle time analysis',
      'Estimate accuracy',
      'Pattern matching',
      'Retrospectives',
    ],
    interactsWith: ['Skill Agent', 'PRD Agent', 'Triage Agent'],
    color: 'primary',
  },
  {
    name: 'Skill Agent',
    icon: 'mdi-account-cog-outline',
    triggerType: 'Daily Cron 02:00',
    triggerIcon: 'mdi-clock-outline',
    tagline: 'Rebuilds skill profiles from git/PRD/bug history, scores 0–1.0, detects bus factor risks.',
    description: 'Rebuilds developer skill profiles daily from git history, PRD assignments, and bug fix records. Generates skill scores (0–1.0) per module, detects bus factor risks, and recommends optimal developer assignments.',
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

const principles = [
  { value: 'AI-generated first drafts', over: 'blank-page paralysis', icon: 'mdi-file-edit-outline' },
  { value: 'Cycle time predictions', over: 'story points & planning poker', icon: 'mdi-chart-timeline-variant' },
  { value: 'Continuous learning', over: 'post-mortems after the damage', icon: 'mdi-brain' },
  { value: 'Human decisions', over: 'human busywork', icon: 'mdi-account-check-outline' },
  { value: 'Living knowledge', over: 'stale Confluence pages', icon: 'mdi-database-sync-outline' },
  { value: 'PRD as single source of truth', over: 'scattered tickets & docs', icon: 'mdi-file-document-check-outline' },
  { value: 'Skills that grow with the team', over: 'static role assignments', icon: 'mdi-trending-up' },
  { value: 'Auto-healing quality loops', over: 'manual bug triage', icon: 'mdi-shield-refresh-outline' },
]

const comparisonRows = [
  { phase: 'Intake', agile: 'Ticket in Jira, manual triage, sprint planning', flowdev: 'Chat message → Triage Agent analyzes, finds duplicates, estimates capacity' },
  { phase: 'Estimation', agile: 'Story points, planning poker, team debate', flowdev: 'AI predicts cycle time from historical features, 85% confidence' },
  { phase: 'Specification', agile: 'PM writes PRD manually, reviews in meetings', flowdev: 'PRD Agent drafts spec with codebase context, enterprise rules, prior art' },
  { phase: 'Design', agile: 'Designer creates in Figma, hands off specs', flowdev: 'Agents scope design, capture Figma review via MCP, auto-generate tech plan' },
  { phase: 'Development', agile: 'Dev picks up ticket, starts from scratch', flowdev: 'AI agent implements on preferred infra, dev does code review' },
  { phase: 'Testing', agile: 'QA writes test cases manually, runs regression', flowdev: 'Auto-generated test plan (unit, integration, e2e, perf, security, UAT)' },
  { phase: 'Bug Mgmt', agile: 'Manual triage, reassign in standup', flowdev: 'Bug Linker auto-links to PRD, >threshold auto-reassigns devs' },
  { phase: 'Deployment', agile: 'Release train, manual status updates', flowdev: 'Status Agent auto-detects PR merges, updates stakeholders' },
  { phase: 'Knowledge', agile: 'Confluence pages go stale, tribal knowledge', flowdev: 'Learning Agent captures patterns, knowledge auto-syncs from code' },
  { phase: 'Skills', agile: 'Manager intuition, annual reviews', flowdev: 'Skill Agent rebuilds daily from git/PRD/bug history, recommends assignments' },
  { phase: 'Retrospective', agile: 'Biweekly meeting, action items forgotten', flowdev: 'Learning Agent auto-generates retrospective on every deployment' },
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
    name: 'Phase 2: PRD Generation',
    icon: 'mdi-file-document-edit-outline',
    description: 'The PRD becomes the single source of truth — containing spec, tech spec, test plan, and acceptance criteria. The PRD Agent searches enterprise rules and prior art to auto-generate all sections.',
    ai: 'Searches enterprise rules & prior art, generates overview, goals, user stories, requirements, acceptance criteria, out of scope, dependencies, risks. Creates PRD folder in repo.',
    human: 'Reviews, refines, and approves PRD.',
  },
  {
    name: 'Phase 3: Design',
    icon: 'mdi-palette-outline',
    description: 'After PRD approval, agents scope design requirements. Each relevant agent provides design input (scope, constraints, patterns). MCP integration captures design review from Figma or preferred design tool.',
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
    description: 'After development, AI auto-generates a comprehensive test plan: automation tests (unit, integration, e2e, performance, security) and manual test cases (UAT scenarios, edge cases, exploratory test guides). All linked to PRD acceptance criteria.',
    ai: 'Generates unit, integration, e2e, performance, and security tests. Creates manual UAT scenarios and exploratory test guides.',
    human: 'Reviews test plan, adds domain-specific edge cases.',
  },
  {
    name: 'Phase 6: QA & UAT',
    icon: 'mdi-clipboard-check-outline',
    description: 'Automated tests execute and manual tests are tracked. The Bug Linker Agent correlates bugs to PRDs via vector search. The Standup Agent provides daily progress reports with flags for lagging PRDs, critical bugs, and scope changes.',
    ai: 'Executes automated tests, correlates bugs to PRDs, generates daily progress reports with risk flags.',
    human: 'Validates quality, runs manual UAT scenarios, signs off on acceptance criteria.',
  },
  {
    name: 'Phase 7: Bug Threshold & Reassignment',
    icon: 'mdi-bug-outline',
    description: 'If bug count exceeds complexity_score × threshold_multiplier, the Reassignment Agent auto-triggers. Original dev is reassigned to bug review, QA moves to next waiting PRD. Post-deploy bugs auto-reopen the PRD with classification.',
    ai: 'Monitors bug threshold, triggers reassignment, auto-classifies bugs as "missed feature" vs "development bug", adds classification to knowledge base.',
    human: 'Reviews reassignment decisions, validates bug classification, can override.',
  },
  {
    name: 'Phase 8: Deployment',
    icon: 'mdi-rocket-launch-outline',
    description: 'The Status Agent auto-detects PR merges and determines status from target branch. PRD folder moves from active/ to deployed/. Stakeholders are notified automatically.',
    ai: 'Detects PR merges, updates PRD status, moves PRD folder, notifies stakeholders.',
    human: 'Gives go/no-go for production deployment.',
  },
  {
    name: 'Phase 9: Learning & Skill Growth',
    icon: 'mdi-brain',
    description: 'The Learning Agent calculates cycle time, compares estimates vs actual, finds patterns across similar features, generates retrospective, and embeds learnings in vector DB. The Skill Agent rebuilds dev profiles daily.',
    ai: 'Calculates cycle time, generates retrospective, detects bus factor alerts, recommends future assignments based on expertise + capacity. Knowledge auto-syncs: code → CLAUDE.md → PostgreSQL → vector search.',
    human: 'Reviews insights, validates learnings, curates enterprise rules.',
  },
]

const aiHandles = [
  'Intake analysis & duplicate detection',
  'PRD drafting with codebase context',
  'Design scope & tech plan generation',
  'Test case generation (automation + manual)',
  'Bug-to-PRD linking & threshold monitoring',
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
  { icon: 'mdi-swap-horizontal', label: 'Auto-Reassignment', detail: 'Original dev moves to bug review, QA moves to next waiting PRD.' },
  { icon: 'mdi-file-restore-outline', label: 'PRD Reopening', detail: 'Post-deployment bugs auto-reopen the PRD for triage.' },
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
  { num: 3, name: 'Central DB', detail: 'PRDs, enterprise rules, architecture decisions (real-time)' },
  { num: 4, name: 'Vector Search', detail: 'Semantic search across everything (auto-indexed)' },
]

const knowledgeAdvantages = [
  'Auto-synced from source — not manually maintained',
  'Semantically searchable — not keyword search',
  'Always current — daily staleness detection',
  'Integrated into agent prompts — agents always have latest context',
]

const skillItems = [
  { icon: 'mdi-history', label: 'Daily Profile Rebuilds', detail: 'Analyzes git history, PRD assignments, and bug fixes to build skill scores (0–1.0) per module.' },
  { icon: 'mdi-alert-outline', label: 'Bus Factor Alerts', detail: 'Detects modules touched by only one person — flags knowledge concentration risk.' },
  { icon: 'mdi-account-arrow-right-outline', label: 'Assignment Recommendations', detail: 'Recommends developers for new PRDs based on expertise match + available capacity.' },
  { icon: 'mdi-trending-up', label: 'Evolving Skills', detail: 'Skills grow automatically as developers contribute — no manual profile updates needed.' },
]

const prdStatuses = ['draft', 'design', 'tech-spec', 'in-dev', 'in-qa', 'in-uat', 'deployed']

const prdFeatures = [
  'Contains spec, tech spec, test plan, acceptance criteria, and metadata',
  'Any status can reopen to draft (e.g., post-deployment bugs)',
  'Bug classification on reopen: "missed feature" vs "development bug"',
  'Full history tracked: status transitions, assignees, reopens, bugs',
  'Vector-indexed for semantic search by all agents',
]
</script>
