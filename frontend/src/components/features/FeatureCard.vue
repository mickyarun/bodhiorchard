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
  <article
    class="feature-card"
    :class="{
      'feature-card--expanded': expanded,
      'feature-card--deactivated': !feature.isActive,
    }"
  >
    <header class="feature-card__head">
      <div class="feature-card__title-row">
        <h3 class="feature-card__title">{{ titleWithoutPrefix }}</h3>
        <div v-if="badges.length" class="feature-card__badges">
          <v-chip
            v-for="badge in badges"
            :key="badge.key"
            size="x-small"
            variant="flat"
            :color="badge.color"
            label
          >
            {{ badge.label }}
          </v-chip>
        </div>
      </div>

      <div class="feature-card__repos">
        <span class="repo-chip repo-chip--primary">
          <v-icon icon="mdi-source-repository" size="13" />
          {{ feature.primary.repoName }}
        </span>
        <span
          v-for="link in feature.backendLinks"
          :key="link.repoId"
          class="repo-chip repo-chip--backend"
          :title="`Depends on ${link.repoName} · ${link.apiPaths.length} API path${
            link.apiPaths.length === 1 ? '' : 's'
          }`"
        >
          <v-icon icon="mdi-arrow-right-thin" size="13" />
          {{ link.repoName }}
        </span>
      </div>

      <div v-if="!feature.isActive && deactivatedSummary" class="feature-card__deactivated-banner">
        <v-icon icon="mdi-archive-outline" size="14" />
        <span>Deactivated {{ deactivatedSummary.dateLabel }}</span>
        <span v-if="deactivatedSummary.prNumber" class="deactivated-banner__sep">·</span>
        <a
          v-if="deactivatedSummary.prNumber && deactivatedSummary.prUrl"
          :href="deactivatedSummary.prUrl"
          target="_blank"
          rel="noopener"
          class="deactivated-banner__pr"
        >
          PR #{{ deactivatedSummary.prNumber }}
          <v-icon icon="mdi-open-in-new" size="11" />
        </a>
        <span v-else-if="deactivatedSummary.prNumber" class="deactivated-banner__pr">
          PR #{{ deactivatedSummary.prNumber }}
        </span>
        <span v-else-if="deactivatedSummary.shortSha" class="deactivated-banner__sha">
          commit
          <code>{{ deactivatedSummary.shortSha }}</code>
        </span>
      </div>
    </header>

    <p class="feature-card__description">{{ feature.description }}</p>

    <div v-if="visibleTags.length" class="feature-card__tags">
      <span v-for="tag in visibleTags" :key="tag" class="feature-tag">{{ tag }}</span>
    </div>

    <div class="feature-card__lineage">
      <span class="lineage-item" :title="createdTooltip">
        <v-icon icon="mdi-plus-circle-outline" size="13" />
        Created {{ createdLabel }}
        <component
          :is="lineage.created.prUrl ? 'a' : 'span'"
          v-if="lineage.created.byLabel"
          :href="lineage.created.prUrl || undefined"
          :target="lineage.created.prUrl ? '_blank' : undefined"
          :rel="lineage.created.prUrl ? 'noopener' : undefined"
          class="lineage-item__by"
          :class="{ 'lineage-item__by--link': !!lineage.created.prUrl }"
        >
          by {{ lineage.created.byLabel }}
          <v-icon v-if="lineage.created.prUrl" icon="mdi-open-in-new" size="10" />
        </component>
      </span>
      <span
        v-if="showLastSeen"
        class="lineage-item lineage-item--separated"
        :title="updatedTooltip"
      >
        <v-icon icon="mdi-update" size="13" />
        Last touched {{ updatedLabel }}
        <component
          :is="lineage.lastSeen.prUrl ? 'a' : 'span'"
          v-if="lineage.lastSeen.byLabel"
          :href="lineage.lastSeen.prUrl || undefined"
          :target="lineage.lastSeen.prUrl ? '_blank' : undefined"
          :rel="lineage.lastSeen.prUrl ? 'noopener' : undefined"
          class="lineage-item__by"
          :class="{ 'lineage-item__by--link': !!lineage.lastSeen.prUrl }"
        >
          by {{ lineage.lastSeen.byLabel }}
          <v-icon v-if="lineage.lastSeen.prUrl" icon="mdi-open-in-new" size="10" />
        </component>
      </span>
    </div>

    <footer class="feature-card__footer">
      <div class="feature-card__meta">
        <span v-if="feature.backendLinks.length > 0" class="meta-pill meta-pill--warning">
          <v-icon icon="mdi-server-network" size="14" />
          {{ feature.backendLinks.length }} backend
          {{ feature.backendLinks.length === 1 ? 'dep' : 'deps' }}
        </span>
      </div>
      <button class="feature-card__toggle" :aria-expanded="expanded" @click="toggle">
        {{ expanded ? 'Hide details' : 'Show details' }}
        <v-icon :icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="16" />
      </button>
    </footer>

    <v-expand-transition>
      <div v-if="expanded" class="feature-card__detail">
        <div class="detail-block">
          <div class="detail-label">Description</div>
          <p class="detail-description">{{ feature.description }}</p>
        </div>

        <div v-if="capabilityList.length > 0" class="detail-block">
          <div class="detail-label">Capabilities</div>
          <ul class="capability-list">
            <li v-for="cap in capabilityList" :key="cap" class="capability-row">
              <v-icon icon="mdi-check-circle-outline" size="14" color="primary" />
              <span>{{ cap }}</span>
            </li>
          </ul>
        </div>

        <div v-if="feature.backendLinks.length > 0" class="detail-block">
          <div class="detail-label">Backend dependencies</div>
          <div class="dep-list">
            <div v-for="link in feature.backendLinks" :key="link.repoId" class="dep-row">
              <div class="dep-row__head">
                <v-icon icon="mdi-arrow-right-bold" size="14" />
                <span class="dep-row__name">{{ link.repoName }}</span>
              </div>
              <div class="dep-row__paths">
                <code v-for="path in link.apiPaths" :key="path" class="api-path">{{ path }}</code>
              </div>
            </div>
          </div>
        </div>

        <div v-if="codeLocationLines.length > 0" class="detail-block">
          <div class="detail-block__head">
            <div class="detail-label">Code locations</div>
            <button
              class="copy-btn"
              :class="{ 'copy-btn--copied': copied }"
              @click="copyLocations"
            >
              <v-icon :icon="copied ? 'mdi-check' : 'mdi-content-copy'" size="13" />
              {{ copied ? 'Copied' : 'Copy' }}
            </button>
          </div>
          <pre class="loc-block"><code>{{ locationText }}</code></pre>
        </div>
      </div>
    </v-expand-transition>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Feature } from '@/types'

const props = defineProps<{ feature: Feature }>()
const expanded = ref(false)
const copied = ref(false)

const titleWithoutPrefix = computed(() =>
  props.feature.featureTitle.replace(/^Feature:\s*/i, '').trim() || props.feature.featureTitle,
)

const visibleTags = computed(() => props.feature.tags.slice(0, 6))

const capabilityList = computed<string[]>(() => {
  const caps = (props.feature.capabilities as Record<string, unknown>)?.capabilities
  if (!Array.isArray(caps)) return []
  return caps.filter((c): c is string => typeof c === 'string')
})

// Color + label per status. Every card surfaces exactly ONE status
// chip so an operator scanning the page can identify lifecycle stage
// at a glance — the prior design left scan-authored rows (NULL
// status) chipless and the user couldn't tell live from in-progress
// just from the card grid.
const STATUS_COLOR: Record<string, string> = {
  planned: 'info',
  in_progress: 'warning',
  implemented: 'success',
}
const STATUS_LABEL: Record<string, string> = {
  planned: 'Planned',
  in_progress: 'In progress',
  implemented: 'Live',
}

const badges = computed(() => {
  const out: Array<{ key: string; label: string; color: string }> = []
  // Lifecycle chip — always present so scanning the grid for
  // in-progress vs live is a first-glance read, not a "click and
  // dig" exercise.
  if (!props.feature.isActive) {
    out.push({ key: 'lifecycle', label: 'Deactivated', color: 'grey-darken-1' })
  } else if (props.feature.featureStatus) {
    out.push({
      key: 'lifecycle',
      label: STATUS_LABEL[props.feature.featureStatus] ?? props.feature.featureStatus,
      color: STATUS_COLOR[props.feature.featureStatus] ?? 'grey',
    })
  } else {
    // Scan-authored rows have NULL feature_status — represent them
    // as ``Live`` because the only way a scan-authored feature
    // exists is if it was synthesised from code that landed on
    // ``main_branch``.
    out.push({ key: 'lifecycle', label: 'Live', color: 'success' })
  }
  if (props.feature.source === 'bud') {
    out.push({ key: 'bud', label: 'BUD', color: 'cyan' })
  }
  return out
})

interface LineageRow {
  // The "by X" suffix — "PR #5" or "baseline scan" or "BUD-021" or
  // "commit abc1234". Null when there's no meaningful provenance to
  // surface (legacy pre-column row with no SHA at all).
  byLabel: string | null
  // Set only when ``byLabel`` is a clickable GitHub PR. The component
  // renders <a> when truthy, <span> otherwise.
  prUrl: string | null
}

interface Lineage {
  created: LineageRow
  lastSeen: LineageRow
}

// Map the backend's creation_mode enum to a human label used in the
// chip/tooltip when the SHA itself doesn't resolve to a tracked PR.
const CREATION_MODE_LABEL: Record<string, string> = {
  full_scan: 'baseline scan',
  bud: 'BUD',
  unknown: 'baseline scan',
  // narrow_synth never reaches this branch — when the row IS a narrow
  // synth, the PR resolution succeeded and we render "PR #N" instead.
}

interface DeactivatedSummary {
  dateLabel: string
  prNumber: number | null
  prUrl: string | null
  shortSha: string | null
}

// Format the deactivation footer. Returns null when the feature is
// active OR when none of the three deactivation fields are populated
// (defensive — the backend always sets at least ``deactivatedAt`` on
// soft-delete, but the type allows null so we narrow here).
const deactivatedSummary = computed<DeactivatedSummary | null>(() => {
  if (props.feature.isActive) return null
  const { deactivatedAt, deactivatedAtSha, deactivatedPrNumber, deactivatedPrUrl } = props.feature
  if (!deactivatedAt && !deactivatedAtSha) return null
  return {
    dateLabel: deactivatedAt ? formatDateShort(deactivatedAt) : 'at unknown date',
    prNumber: deactivatedPrNumber,
    prUrl: deactivatedPrUrl,
    // Fall back to the 7-char short SHA when the PR lookup didn't
    // resolve (e.g. force-push merge, deleted PR). At least the
    // operator can find the commit on GitHub manually.
    shortSha: !deactivatedPrNumber && deactivatedAtSha ? deactivatedAtSha.slice(0, 7) : null,
  }
})

function formatDateShort(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    })
  } catch {
    return iso
  }
}

function formatDateTimeForTitle(iso: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

// Build the "by X" suffix for one lineage row. Order of preference:
// (1) tracked PR → "PR #N" link, (2) BUD source → "BUD-XXX", (3)
// raw SHA fallback → "commit abc1234", (4) creation-mode label
// ("baseline scan"). Returns ``{byLabel: null, prUrl: null}`` when
// nothing meaningful can be surfaced.
function buildLineageRow(
  prNumber: number | null,
  prUrl: string | null,
  sha: string | null,
  modeLabel: string | null,
  budSourceRef: string | null,
): LineageRow {
  if (prNumber !== null) {
    return { byLabel: `PR #${prNumber}`, prUrl }
  }
  if (budSourceRef) {
    return { byLabel: budSourceRef, prUrl: null }
  }
  if (sha) {
    // SHA didn't resolve to a tracked PR — show short SHA + the
    // creation-mode in parentheses so operators can tell apart "this
    // came from a baseline scan" vs "this SHA exists but the PR was
    // force-pushed/external".
    if (modeLabel) {
      return { byLabel: `${modeLabel} (${sha.slice(0, 7)})`, prUrl: null }
    }
    return { byLabel: `commit ${sha.slice(0, 7)}`, prUrl: null }
  }
  if (modeLabel) {
    return { byLabel: modeLabel, prUrl: null }
  }
  return { byLabel: null, prUrl: null }
}

const lineage = computed<Lineage>(() => {
  const f = props.feature
  const modeLabel =
    f.creationMode === 'narrow_synth' ? null : (CREATION_MODE_LABEL[f.creationMode] ?? null)
  return {
    created: buildLineageRow(
      f.createdPrNumber,
      f.createdPrUrl,
      f.createdAtSha,
      modeLabel,
      f.source === 'bud' ? f.sourceRef : null,
    ),
    // The "last touched" row resolves independently; no mode label
    // (the row's mode is about CREATION). We only show the BUD ref on
    // creation, never on last-touched, since BUDs don't drive
    // reconciler updates.
    lastSeen: buildLineageRow(
      f.lastSeenPrNumber,
      f.lastSeenPrUrl,
      f.lastSeenSha,
      null,
      null,
    ),
  }
})

const createdLabel = computed(() => formatDateShort(props.feature.createdAt))
const updatedLabel = computed(() => formatDateShort(props.feature.updatedAt))
const createdTooltip = computed(() => formatDateTimeForTitle(props.feature.createdAt))
const updatedTooltip = computed(() => formatDateTimeForTitle(props.feature.updatedAt))

// Suppress the "Last touched" half when it's redundant with creation:
// a brand-new row that's never been re-touched has identical
// timestamps + SHA, and showing both reads as visual noise.
const showLastSeen = computed(() => {
  const f = props.feature
  if (!f.lastSeenSha) return false
  if (f.createdAtSha === f.lastSeenSha && f.createdAt === f.updatedAt) {
    return false
  }
  return true
})

interface LocationLine {
  layer: string
  path: string
}

const codeLocationLines = computed<LocationLine[]>(() => {
  const merged = new Map<string, Set<string>>()
  const ingest = (locs: Record<string, string[]> | null | undefined): void => {
    if (!locs) return
    for (const [layer, paths] of Object.entries(locs)) {
      if (!Array.isArray(paths)) continue
      const set = merged.get(layer) ?? new Set<string>()
      for (const p of paths) if (typeof p === 'string') set.add(p)
      merged.set(layer, set)
    }
  }
  ingest(props.feature.primary.codeLocations)
  for (const link of props.feature.backendLinks) ingest(link.codeLocations)
  const lines: LocationLine[] = []
  for (const [layer, paths] of merged.entries()) {
    for (const path of [...paths].sort()) lines.push({ layer, path })
  }
  return lines
})

const locationText = computed(() => {
  const byLayer = new Map<string, string[]>()
  for (const { layer, path } of codeLocationLines.value) {
    const list = byLayer.get(layer) ?? []
    list.push(path)
    byLayer.set(layer, list)
  }
  return Array.from(byLayer.entries())
    .map(([layer, paths]) => `# ${layer}\n${paths.join('\n')}`)
    .join('\n\n')
})

function toggle(): void {
  expanded.value = !expanded.value
}

async function copyLocations(): Promise<void> {
  try {
    await navigator.clipboard.writeText(locationText.value)
    copied.value = true
    setTimeout(() => {
      copied.value = false
    }, 1500)
  } catch {
    /* clipboard unavailable — surface nothing rather than alert spam */
  }
}
</script>

<style scoped>
.feature-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px 18px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.15s ease, background 0.15s ease;
}
.feature-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.45);
  background: rgba(255, 255, 255, 0.04);
}
.feature-card--expanded {
  border-color: rgba(var(--v-theme-primary), 0.6);
  background: rgba(255, 255, 255, 0.05);
}
.feature-card--deactivated {
  /* Soft-deleted rows render with reduced contrast so the eye drops
     to active features first; the dashed left rail is the at-a-glance
     "this no longer exists" marker that survives the dim. */
  opacity: 0.72;
  border-style: dashed;
  border-left: 3px solid rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.012);
}
.feature-card--deactivated:hover {
  opacity: 0.95;
  border-color: rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.025);
}
.feature-card--deactivated .feature-card__title {
  color: rgba(255, 255, 255, 0.75);
}

.feature-card__deactivated-banner {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.65);
  font-size: 0.74rem;
  line-height: 1.3;
}
.deactivated-banner__sep {
  opacity: 0.4;
}
.deactivated-banner__pr {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: rgba(var(--v-theme-primary), 1);
  text-decoration: none;
  font-weight: 500;
}
.deactivated-banner__pr:hover {
  text-decoration: underline;
}
.deactivated-banner__sha code {
  font-family: ui-monospace, SFMono-Regular, monospace;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.78);
  font-size: 0.72rem;
}

.feature-card__head {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.feature-card__title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.feature-card__title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.35;
  color: rgba(255, 255, 255, 0.95);
  letter-spacing: 0.005em;
}
.feature-card__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  flex-shrink: 0;
}

.feature-card__repos {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.repo-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 0.01em;
  white-space: nowrap;
}
.repo-chip--primary {
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgba(var(--v-theme-primary), 1);
  border: 1px solid rgba(var(--v-theme-primary), 0.3);
}
.repo-chip--backend {
  background: rgba(var(--v-theme-warning), 0.12);
  color: rgba(var(--v-theme-warning), 1);
  border: 1px solid rgba(var(--v-theme-warning), 0.25);
  cursor: help;
}

.feature-card__description {
  margin: 0;
  color: rgba(255, 255, 255, 0.72);
  font-size: 0.875rem;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.feature-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.feature-tag {
  font-size: 0.7rem;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.08);
  letter-spacing: 0.02em;
}

.feature-card__lineage {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  align-items: center;
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.48);
  line-height: 1.3;
}
.lineage-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.lineage-item--separated {
  /* Vertical bar between created/last-touched so the two halves read
     as a single timeline rather than two unrelated chips. */
  border-left: 1px solid rgba(255, 255, 255, 0.08);
  padding-left: 14px;
}
.lineage-item__by {
  color: rgba(255, 255, 255, 0.62);
  text-decoration: none;
  margin-left: 2px;
  font-weight: 500;
}
.lineage-item__by--link {
  color: rgba(var(--v-theme-primary), 0.92);
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.lineage-item__by--link:hover {
  text-decoration: underline;
  color: rgba(var(--v-theme-primary), 1);
}

.feature-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 8px;
  border-top: 1px dashed rgba(255, 255, 255, 0.06);
}
.feature-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.meta-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.72rem;
  padding: 3px 8px;
  border-radius: 4px;
  font-weight: 500;
}
.meta-pill--primary {
  background: rgba(var(--v-theme-primary), 0.12);
  color: rgba(var(--v-theme-primary), 1);
}
.meta-pill--warning {
  background: rgba(var(--v-theme-warning), 0.15);
  color: rgba(var(--v-theme-warning), 1);
}
.feature-card__toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  color: rgba(var(--v-theme-primary), 1);
  font-size: 0.78rem;
  font-weight: 500;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.feature-card__toggle:hover {
  background: rgba(var(--v-theme-primary), 0.1);
}

.feature-card__detail {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 8px;
}
.detail-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.detail-block__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.detail-label {
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(255, 255, 255, 0.5);
}

.detail-description {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.55;
  color: rgba(255, 255, 255, 0.82);
  white-space: pre-wrap;
  word-break: break-word;
}

.capability-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.capability-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.82);
  line-height: 1.5;
}
.capability-row > .v-icon {
  flex-shrink: 0;
  margin-top: 3px;
}

.dep-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dep-row__head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 0.85rem;
  font-weight: 500;
}
.dep-row__name {
  color: rgba(var(--v-theme-warning), 1);
}
.dep-row__paths {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding-left: 20px;
}
.api-path {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.72rem;
  padding: 2px 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.copy-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.75);
  font-size: 0.7rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}
.copy-btn:hover {
  background: rgba(var(--v-theme-primary), 0.15);
  color: rgba(var(--v-theme-primary), 1);
  border-color: rgba(var(--v-theme-primary), 0.4);
}
.copy-btn--copied {
  background: rgba(var(--v-theme-success), 0.15);
  color: rgba(var(--v-theme-success), 1);
  border-color: rgba(var(--v-theme-success), 0.4);
}

.loc-block {
  margin: 0;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.28);
  border: 1px solid rgba(255, 255, 255, 0.06);
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.72rem;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.78);
  max-height: 220px;
  overflow: auto;
  white-space: pre;
}
.loc-block code {
  display: block;
  font-family: inherit;
  background: transparent;
  color: inherit;
}
</style>
