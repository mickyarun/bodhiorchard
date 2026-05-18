<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<template>
  <div class="bud-timeline">
    <div v-if="loading" class="d-flex justify-center py-6">
      <v-progress-circular indeterminate size="24" />
    </div>
    <div v-else-if="events.length === 0" class="text-center text-medium-emphasis py-6">
      No activity yet
    </div>
    <v-timeline v-else density="compact" side="end" truncate-line="both">
      <v-timeline-item
        v-for="event in events"
        :key="event.id"
        :dot-color="eventConfig(event.event_type).color"
        :icon="eventConfig(event.event_type).icon"
        size="x-small"
      >
        <div class="tl-row">
          <div class="tl-content">
            <!-- Created -->
            <template v-if="event.event_type === 'created'">
              <div class="tl-primary">
                <span v-if="event.actor_name" class="tl-actor">{{ event.actor_name }}</span>
                <span>created this BUD</span>
              </div>
              <div v-if="event.detail?.source === 'slack_triage'" class="tl-meta">
                <v-chip size="x-small" color="indigo" variant="tonal" label class="tl-badge">
                  <v-icon start size="10">mdi-slack</v-icon>
                  Slack triage
                </v-chip>
              </div>
            </template>

            <!-- Requested (Slack) -->
            <template v-else-if="event.event_type === 'requested'">
              <div class="tl-primary">
                <span>Requested by</span>
                <span class="tl-actor">{{ event.detail?.requester_name ?? 'unknown' }}</span>
              </div>
              <div class="tl-meta">
                <v-chip size="x-small" color="indigo" variant="tonal" label class="tl-badge">
                  <v-icon start size="10">mdi-slack</v-icon>
                  {{ event.detail?.channel ?? 'Slack' }}
                </v-chip>
              </div>
            </template>

            <!-- Approved -->
            <template v-else-if="event.event_type === 'approved'">
              <div class="tl-primary">
                <span class="tl-actor">{{ event.detail?.approver_name ?? event.actor_name ?? 'Unknown' }}</span>
                <span>approved this feature</span>
              </div>
            </template>

            <!-- Status Change -->
            <template v-else-if="event.event_type === 'status_change'">
              <div class="tl-primary">
                <span v-if="event.actor_name" class="tl-actor">{{ event.actor_name }}</span>
                <span>moved</span>
                <v-chip
                  :color="statusColor(String(event.detail?.from ?? ''))"
                  size="x-small"
                  variant="tonal"
                  label
                  class="tl-status-chip"
                >
                  {{ statusLabel(String(event.detail?.from ?? '')) }}
                </v-chip>
                <v-icon size="12" class="tl-arrow">mdi-arrow-right</v-icon>
                <v-chip
                  :color="statusColor(String(event.detail?.to ?? ''))"
                  size="x-small"
                  variant="tonal"
                  label
                  class="tl-status-chip"
                >
                  {{ statusLabel(String(event.detail?.to ?? '')) }}
                </v-chip>
              </div>
            </template>

            <!-- Assigned -->
            <template v-else-if="event.event_type === 'assigned'">
              <div class="tl-primary">
                <span>Assigned to</span>
                <span class="tl-actor">{{ event.detail?.assignee_name ?? 'unknown' }}</span>
              </div>
              <div class="tl-meta">
                <v-chip
                  v-if="event.detail?.role"
                  size="x-small"
                  variant="outlined"
                  label
                  class="tl-badge"
                >
                  {{ formatRole(String(event.detail.role)) }}
                </v-chip>
                <v-chip
                  v-if="event.detail?.method === 'auto_round_robin'"
                  size="x-small"
                  color="teal"
                  variant="tonal"
                  label
                  class="tl-badge"
                >
                  <v-icon start size="10">mdi-autorenew</v-icon>
                  auto
                </v-chip>
                <v-chip
                  v-else-if="event.detail?.method === 'manual'"
                  size="x-small"
                  variant="tonal"
                  label
                  class="tl-badge"
                >
                  manual
                </v-chip>
                <v-chip
                  v-else-if="event.detail?.method === 'continuity'"
                  size="x-small"
                  color="primary"
                  variant="tonal"
                  label
                  class="tl-badge"
                  :title="continuityTooltip(event.detail)"
                >
                  <v-icon start size="10">mdi-restart</v-icon>
                  continuity
                </v-chip>
              </div>
            </template>

            <!-- Unassigned -->
            <template v-else-if="event.event_type === 'unassigned'">
              <div class="tl-primary">
                <span v-if="event.actor_name" class="tl-actor">{{ event.actor_name }}</span>
                <span>removed assignment</span>
              </div>
            </template>

            <!-- AI Agent Completed -->
            <template v-else-if="event.event_type === 'ai_agent_completed'">
              <div class="tl-primary">
                <v-icon size="14" color="success" class="mr-1">mdi-check-circle</v-icon>
                <span>AI</span>
                <v-chip size="x-small" color="deep-purple" variant="tonal" label class="tl-badge">
                  {{ formatAgent(String(event.detail?.agent ?? 'agent')) }}
                </v-chip>
                <span>completed on</span>
                <span class="tl-section">{{ formatSection(String(event.detail?.section ?? '')) }}</span>
              </div>
            </template>

            <!-- AI Agent Failed -->
            <template v-else-if="event.event_type === 'ai_agent_failed'">
              <div class="tl-primary">
                <v-icon size="14" color="error" class="mr-1">mdi-alert-circle</v-icon>
                <span>AI</span>
                <v-chip size="x-small" color="deep-purple" variant="tonal" label class="tl-badge">
                  {{ formatAgent(String(event.detail?.agent ?? 'agent')) }}
                </v-chip>
                <span class="text-error">failed</span>
                <span>on</span>
                <span class="tl-section">{{ formatSection(String(event.detail?.section ?? '')) }}</span>
              </div>
            </template>

            <!-- Design Generated -->
            <template v-else-if="event.event_type === 'design_generated'">
              <div class="tl-primary">
                <span>Design wireframe generated</span>
              </div>
              <div v-if="event.detail?.repo_id" class="tl-meta">
                <v-chip size="x-small" color="teal" variant="tonal" label class="tl-badge">
                  <v-icon start size="10">mdi-source-repository</v-icon>
                  repo
                </v-chip>
              </div>
            </template>

            <!-- Feature link events -->
            <template v-else-if="event.event_type === 'feature_linked'">
              <div class="tl-primary">
                <span v-if="event.actor_name" class="tl-actor">{{ event.actor_name }}</span>
                <span>linked</span>
                <span class="tl-section">{{ formatFeatureTitles(event.detail) }}</span>
              </div>
            </template>

            <template v-else-if="event.event_type === 'feature_unlinked'">
              <div class="tl-primary">
                <span v-if="event.actor_name" class="tl-actor">{{ event.actor_name }}</span>
                <span>unlinked</span>
                <span class="tl-section">{{ formatSingleFeatureTitle(event.detail) }}</span>
              </div>
            </template>

            <template v-else-if="event.event_type === 'features_auto_linked'">
              <div class="tl-primary">
                <span class="tl-actor">PM Agent</span>
                <span>auto-linked</span>
                <span class="tl-section">{{ formatFeatureTitles(event.detail) }}</span>
              </div>
            </template>

            <!-- Content Updated -->
            <template v-else-if="event.event_type === 'content_updated'">
              <div class="tl-primary">
                <span v-if="event.actor_name" class="tl-actor">{{ event.actor_name }}</span>
                <span>updated</span>
                <span class="tl-section">{{ formatSection(String(event.detail?.section ?? '')) }}</span>
              </div>
            </template>

            <!-- PR Events -->
            <template v-else-if="event.event_type === 'pr_opened' || event.event_type === 'pr_merged'">
              <div class="tl-primary">
                <span>PR #{{ event.detail?.pr_number }}</span>
                <span>{{ event.event_type === 'pr_opened' ? 'opened' : 'merged' }} on</span>
                <span class="tl-section">{{ event.detail?.repo }}</span>
              </div>
              <div v-if="event.detail?.html_url" class="tl-meta">
                <a :href="String(event.detail.html_url)" target="_blank" class="text-caption">
                  View on GitHub
                  <v-icon size="10">mdi-open-in-new</v-icon>
                </a>
              </div>
            </template>

            <template v-else-if="event.event_type === 'all_prs_merged'">
              <div class="tl-primary">
                <span>All PRs merged — ready for testing</span>
              </div>
            </template>

            <!-- Estimation events -->
            <template v-else-if="event.event_type === 'estimate_generated'">
              <div class="tl-primary">
                <span>AI estimated PROD by {{ formatShortDate(event.detail?.prod_p70 as string | null | undefined) }}</span>
                <span class="tl-meta">({{ event.detail?.trigger }})</span>
              </div>
              <div v-if="event.detail?.complexity" class="tl-meta">
                Complexity: {{ event.detail.complexity }}/5
              </div>
            </template>

            <template v-else-if="event.event_type === 'estimate_overridden'">
              <div class="tl-primary">
                <span v-if="event.actor_name" class="tl-actor">{{ event.actor_name }}</span>
                <span>overrode {{ event.detail?.phase }} deadline to {{ formatShortDate(event.detail?.new_date as string | null | undefined) }}</span>
              </div>
              <div v-if="event.detail?.reason" class="tl-meta">
                Reason: {{ event.detail.reason }}
              </div>
            </template>

            <!-- AC Verification -->
            <template v-else-if="event.event_type === 'ac_verification_passed'">
              <div class="tl-primary">
                <span>All {{ event.detail?.total }} acceptance criteria verified</span>
              </div>
            </template>

            <template v-else-if="event.event_type === 'ac_verification_failed'">
              <div class="tl-primary text-error">
                <span>{{ event.detail?.passed }}/{{ event.detail?.total }} acceptance criteria verified</span>
              </div>
              <div v-if="event.detail?.results" class="tl-meta">
                <div v-for="(r, i) in (event.detail.results as Array<Record<string, unknown>>).filter(r => !r.implemented)" :key="i" class="text-caption">
                  Missing: {{ r.criterion }}
                </div>
              </div>
            </template>

            <!-- Status Override -->
            <template v-else-if="event.event_type === 'status_override'">
              <div class="tl-primary">
                <span v-if="event.actor_name" class="tl-actor">{{ event.actor_name }}</span>
                <span>manually advanced to {{ event.detail?.to }}</span>
              </div>
              <div v-if="event.detail?.reason" class="tl-meta">
                Reason: {{ event.detail.reason }}
              </div>
            </template>

            <!-- Fallback -->
            <template v-else>
              <div class="tl-primary">
                <span v-if="event.actor_name" class="tl-actor">{{ event.actor_name }}</span>
                <span>{{ eventConfig(event.event_type).label }}</span>
              </div>
            </template>
          </div>

          <span class="tl-time" :title="fullTime(event.created_at)">{{ formatTime(event.created_at) }}</span>
        </div>
      </v-timeline-item>
    </v-timeline>
  </div>
</template>

<script setup lang="ts">
import type { TimelineEvent, BUDStatus } from '@/types'
import { BUD_STATUS_LABELS, BUD_STATUS_COLORS } from '@/types'

defineProps<{
  events: TimelineEvent[]
  loading: boolean
}>()

interface EventConfig {
  icon: string
  color: string
  label: string
}

const EVENT_MAP: Record<string, EventConfig> = {
  created: { icon: 'mdi-plus-circle', color: 'success', label: 'BUD created' },
  requested: { icon: 'mdi-message-text', color: 'info', label: 'Requested' },
  approved: { icon: 'mdi-check-decagram', color: 'success', label: 'Approved' },
  status_change: { icon: 'mdi-swap-horizontal', color: 'primary', label: 'Status changed' },
  assigned: { icon: 'mdi-account-check', color: 'teal', label: 'Assigned' },
  unassigned: { icon: 'mdi-account-remove', color: 'grey', label: 'Unassigned' },
  ai_agent_started: { icon: 'mdi-robot', color: 'blue', label: 'AI started' },
  ai_agent_completed: { icon: 'mdi-robot', color: 'success', label: 'AI completed' },
  ai_agent_failed: { icon: 'mdi-robot-off', color: 'error', label: 'AI failed' },
  content_updated: { icon: 'mdi-pencil', color: 'primary', label: 'Content updated' },
  design_generated: { icon: 'mdi-palette', color: 'teal', label: 'Design generated' },
  comment: { icon: 'mdi-comment-text', color: 'grey', label: 'Comment' },
  pr_opened: { icon: 'mdi-source-pull', color: 'info', label: 'PR opened' },
  pr_merged: { icon: 'mdi-source-merge', color: 'success', label: 'PR merged' },
  all_prs_merged: { icon: 'mdi-check-all', color: 'success', label: 'All PRs merged' },
  estimate_generated: { icon: 'mdi-chart-timeline-variant', color: 'blue', label: 'Estimate updated' },
  estimate_overridden: { icon: 'mdi-calendar-edit', color: 'orange', label: 'Estimate overridden' },
  ac_verification_passed: { icon: 'mdi-check-decagram', color: 'success', label: 'ACs verified' },
  ac_verification_failed: { icon: 'mdi-alert-circle', color: 'error', label: 'ACs incomplete' },
  status_override: { icon: 'mdi-shield-alert', color: 'orange', label: 'Manual override' },
  feature_linked: { icon: 'mdi-link-plus', color: 'teal', label: 'Feature linked' },
  feature_unlinked: { icon: 'mdi-link-off', color: 'grey', label: 'Feature unlinked' },
  features_auto_linked: { icon: 'mdi-robot', color: 'teal', label: 'Features auto-linked' },
}

const DEFAULT_CONFIG: EventConfig = { icon: 'mdi-circle-small', color: 'grey', label: 'Event' }

const ROLE_LABELS: Record<string, string> = {
  pm: 'Product Manager',
  designer: 'Designer',
  developer: 'Developer',
  qa: 'QA Engineer',
  tech_lead: 'Tech Lead',
  admin: 'Admin',
  org_owner: 'Owner',
}

const SECTION_LABELS: Record<string, string> = {
  requirements_md: 'Requirements',
  tech_spec_md: 'Tech Spec',
  test_plan_md: 'Test Plan',
  design: 'Design',
  title: 'Title',
}

const AGENT_LABELS: Record<string, string> = {
  'product-manager': 'PM Agent',
  'designer': 'Design Agent',
  'qa-engineer': 'QA Agent',
  'tech-planner': 'Tech Planner',
  'test-planner': 'Test Planner',
}

function eventConfig(type: string): EventConfig {
  return EVENT_MAP[type] ?? DEFAULT_CONFIG
}

function statusColor(s: string): string {
  return BUD_STATUS_COLORS[s as BUDStatus] ?? 'grey'
}

function statusLabel(s: string): string {
  return BUD_STATUS_LABELS[s as BUDStatus] ?? s.toUpperCase()
}

function formatRole(role: string): string {
  return ROLE_LABELS[role] ?? role
}

function continuityTooltip(detail: Record<string, unknown> | null | undefined): string {
  if (!detail) return 'Carried over from a previous phase'
  const from = detail.continuity_from_role
  if (typeof from === 'string' && from) {
    return `Carried over from previous ${formatRole(from)}`
  }
  return 'Carried over from a previous phase'
}

function formatSection(section: string): string {
  return SECTION_LABELS[section] ?? section
}

function formatAgent(agent: string): string {
  return AGENT_LABELS[agent] ?? agent
}

// Render the titles list on feature_linked / features_auto_linked events.
// Trims empties (backend writes "" when a title can't be resolved), shows the
// first two by name, and falls back to a "N features" count when the detail
// is missing entirely (older events written before titles were captured).
const MAX_TITLES_INLINE = 2
function formatFeatureTitles(detail: Record<string, unknown> | undefined | null): string {
  const titles = Array.isArray(detail?.feature_titles)
    ? (detail.feature_titles as unknown[]).map(String).filter(t => t.length > 0)
    : []
  const count = Number(detail?.count ?? titles.length)
  if (titles.length === 0) {
    return count === 1 ? '1 feature' : `${count} features`
  }
  if (titles.length <= MAX_TITLES_INLINE) {
    return titles.join(', ')
  }
  const head = titles.slice(0, MAX_TITLES_INLINE).join(', ')
  const rest = titles.length - MAX_TITLES_INLINE
  return `${head} and ${rest} more`
}

function formatSingleFeatureTitle(detail: Record<string, unknown> | undefined | null): string {
  const title = typeof detail?.feature_title === 'string' ? detail.feature_title : ''
  return title.length > 0 ? title : 'a feature'
}

function formatShortDate(dateStr: string | undefined | null): string {
  if (!dateStr) return '—'
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHrs = Math.floor(diffMins / 60)
  if (diffHrs < 24) return `${diffHrs}h ago`
  const diffDays = Math.floor(diffHrs / 24)
  if (diffDays < 7) return `${diffDays}d ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function fullTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.bud-timeline {
  padding: 8px 0;
}

/* Row layout: content left, time right */
.tl-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  min-height: 28px;
}

.tl-content {
  flex: 1;
  min-width: 0;
}

/* Primary line: inline text + chips */
.tl-primary {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 13px;
  line-height: 1.5;
  color: rgba(var(--v-theme-on-surface), 0.75);
}

/* Actor name: bold */
.tl-actor {
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.9);
}

/* Section name: italic emphasis */
.tl-section {
  font-style: italic;
  color: rgba(var(--v-theme-on-surface), 0.6);
}

/* Arrow between status chips */
.tl-arrow {
  color: rgba(var(--v-theme-on-surface), 0.35);
  margin: 0 1px;
}

/* Status chips: tighter padding */
.tl-status-chip {
  font-size: 11px !important;
  height: 18px !important;
  padding: 0 6px !important;
}

/* Meta line: badges below primary */
.tl-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
}

.tl-badge {
  font-size: 10px !important;
  height: 18px !important;
  padding: 0 6px !important;
  letter-spacing: 0.02em;
}

/* Timestamp: right-aligned, muted */
.tl-time {
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.35);
  white-space: nowrap;
  padding-top: 2px;
  cursor: default;
}
</style>
