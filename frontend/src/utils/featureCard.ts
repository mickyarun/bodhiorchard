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

/** What a feature card shows, derived from the API row. */
import type { Feature } from '@/types'
import { formatDate } from '@/utils/date'

export interface FeatureLifecycle {
  label: string
  /** Theme colour name for the tag. */
  color: string
}

/** "Feature: Billing export" → "Billing export". */
export function featureDisplayTitle(feature: Pick<Feature, 'featureTitle'>): string {
  return feature.featureTitle.replace(/^Feature:\s*/i, '').trim() || feature.featureTitle
}

const LIFECYCLE: Record<string, FeatureLifecycle> = {
  planned: { label: 'Planned', color: 'info' },
  in_progress: { label: 'In progress', color: 'warning' },
  implemented: { label: 'Live', color: 'success' },
}

/**
 * One lifecycle tag per card. Scan-authored rows have no status: they only
 * exist because the code is on the main branch, so they read as Live.
 */
export function featureLifecycle(feature: Pick<Feature, 'isActive' | 'featureStatus'>): FeatureLifecycle {
  if (!feature.isActive) return { label: 'Deactivated', color: 'muted' }
  if (!feature.featureStatus) return LIFECYCLE.implemented
  return LIFECYCLE[feature.featureStatus] ?? { label: feature.featureStatus, color: 'muted' }
}

/** Capability strings from the free-form capabilities blob. */
export function featureCapabilities(feature: Pick<Feature, 'capabilities'>): string[] {
  const caps = (feature.capabilities as Record<string, unknown> | null)?.capabilities
  return Array.isArray(caps) ? caps.filter((c): c is string => typeof c === 'string') : []
}

export interface LineageRow {
  /** "PR #5", "BUD-021", "baseline scan (abc1234)", "commit abc1234"; null when unknown. */
  byLabel: string | null
  /** Set only when ``byLabel`` is a tracked PR. */
  prUrl: string | null
}

const CREATION_MODE_LABEL: Record<string, string> = {
  full_scan: 'baseline scan',
  bud: 'BUD',
  unknown: 'baseline scan',
}

/** Preference: tracked PR, then the BUD it came from, then the SHA, then how it was made. */
export function lineageRow(
  prNumber: number | null,
  prUrl: string | null,
  sha: string | null,
  modeLabel: string | null,
  budRef: string | null,
): LineageRow {
  if (prNumber !== null) return { byLabel: `PR #${prNumber}`, prUrl }
  if (budRef) return { byLabel: budRef, prUrl: null }
  if (sha) {
    const short = sha.slice(0, 7)
    return { byLabel: modeLabel ? `${modeLabel} (${short})` : `commit ${short}`, prUrl: null }
  }
  return { byLabel: modeLabel, prUrl: null }
}

export function featureLineage(f: Feature): { created: LineageRow; lastSeen: LineageRow } {
  const modeLabel = f.creationMode === 'narrow_synth' ? null : (CREATION_MODE_LABEL[f.creationMode] ?? null)
  return {
    created: lineageRow(f.createdPrNumber, f.createdPrUrl, f.createdAtSha, modeLabel, f.source === 'bud' ? f.sourceRef : null),
    // Mode and BUD describe creation only; later touches come from merges.
    lastSeen: lineageRow(f.lastSeenPrNumber, f.lastSeenPrUrl, f.lastSeenSha, null, null),
  }
}

/** Hide "Last touched" when the row was never touched after it was made. */
export function showLastTouched(f: Feature): boolean {
  if (!f.lastSeenSha) return false
  return !(f.createdAtSha === f.lastSeenSha && f.createdAt === f.updatedAt)
}

export interface DeactivatedSummary {
  dateLabel: string
  prNumber: number | null
  prUrl: string | null
  shortSha: string | null
}

export function deactivatedSummary(f: Feature): DeactivatedSummary | null {
  if (f.isActive || (!f.deactivatedAt && !f.deactivatedAtSha)) return null
  return {
    dateLabel: f.deactivatedAt ? formatDate(f.deactivatedAt) : 'at an unknown date',
    prNumber: f.deactivatedPrNumber,
    prUrl: f.deactivatedPrUrl,
    // The SHA is the fallback when the merge didn't resolve to a PR.
    shortSha: !f.deactivatedPrNumber && f.deactivatedAtSha ? f.deactivatedAtSha.slice(0, 7) : null,
  }
}

/** Code locations from the primary repo and every backend link, by layer, paths sorted and de-duplicated. */
export function codeLocations(f: Feature): Map<string, string[]> {
  const merged = new Map<string, Set<string>>()
  const ingest = (locs: Record<string, string[]> | null | undefined): void => {
    for (const [layer, paths] of Object.entries(locs ?? {})) {
      if (!Array.isArray(paths)) continue
      const set = merged.get(layer) ?? new Set<string>()
      for (const p of paths) if (typeof p === 'string') set.add(p)
      merged.set(layer, set)
    }
  }
  ingest(f.primary?.codeLocations)
  for (const link of f.backendLinks) ingest(link.codeLocations)
  return new Map([...merged].map(([layer, set]) => [layer, [...set].sort()]))
}

/** "# layer\npath\npath\n\n# layer\n…" for the copy button. */
export function codeLocationsText(locations: Map<string, string[]>): string {
  return [...locations].map(([layer, paths]) => `# ${layer}\n${paths.join('\n')}`).join('\n\n')
}

/** Description length past which the card clamps it and offers to show the rest. */
export const LONG_DESCRIPTION = 200

/** Whether "Show details" would reveal anything. */
export function featureHasDetail(f: Feature): boolean {
  return (
    f.description.length > LONG_DESCRIPTION ||
    f.backendLinks.length > 0 ||
    featureCapabilities(f).length > 0 ||
    codeLocations(f).size > 0
  )
}
