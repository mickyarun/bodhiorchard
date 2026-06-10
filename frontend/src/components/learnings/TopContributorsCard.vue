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

<!--
  Top contributors over the last 30 days. Rows show: rank, deterministic
  avatar (hash(user_id) → hue so the same person renders consistently),
  name + stats line, and a horizontal bar proportional to the top
  contributor's BUDs-shipped count.
-->

<template>
  <section class="card">
    <header class="card__head">
      <v-icon icon="mdi-account-group-outline" size="18" color="primary" />
      <div class="card__title">Top contributors</div>
      <div class="card__sub">
        Last 30 days. Ranked by BUDs shipped; commits and PRs are
        the per-contributor totals across those BUDs.
      </div>
    </header>
    <div v-if="contributors.length === 0" class="empty-row">
      No closures with contributors recorded in the last 30 days.
    </div>
    <div v-else class="contrib-list">
      <article
        v-for="(row, idx) in contributors"
        :key="row.user_id"
        class="contrib"
      >
        <div class="contrib-rank">{{ idx + 1 }}</div>
        <div class="contrib-avatar" :style="avatarStyle(row.user_id)">
          {{ initials(row.name) }}
        </div>
        <div class="contrib-info">
          <div class="contrib-name">{{ row.name }}</div>
          <div class="contrib-stats">
            {{ row.buds_shipped_30d }}
            BUD{{ row.buds_shipped_30d === 1 ? '' : 's' }} ·
            {{ row.total_commits_30d }} commits ·
            {{ row.total_prs_merged_30d }} PRs
          </div>
        </div>
        <div class="contrib-bar-wrap">
          <div
            class="contrib-bar"
            :style="{ width: `${contributorPct(row)}%` }"
          />
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { TopContributor } from '@/composables/useLearningsOverview'

const props = defineProps<{ contributors: TopContributor[] }>()

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).slice(0, 2)
  return parts.map((p) => p[0] || '').join('').toUpperCase() || '?'
}

function avatarStyle(seed: string): { background: string } {
  // Deterministic tint per user_id so the same contributor always
  // shows the same avatar colour across renders. Hash → hue, fixed
  // saturation / lightness keeps the palette inside the design system.
  let hash = 0
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) & 0xffff
  const hue = hash % 360
  return { background: `hsl(${hue}, 55%, 30%)` }
}

function contributorPct(row: TopContributor): number {
  const top = Math.max(1, ...props.contributors.map((c) => c.buds_shipped_30d))
  return Math.max(4, Math.round((row.buds_shipped_30d / top) * 100))
}
</script>

<style scoped>
.card {
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  padding: 18px 20px 20px;
  background: rgb(var(--v-theme-surface));
}

.card__head {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 10px;
  row-gap: 2px;
  margin-bottom: 14px;
}

.card__head > .v-icon {
  grid-row: 1 / span 2;
  align-self: start;
  margin-top: 2px;
}

.card__title {
  font-size: 15px;
  font-weight: 500;
}

.card__sub {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.85;
  max-width: 720px;
}

.empty-row {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  padding: 6px 2px;
}

.contrib-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.contrib {
  display: grid;
  grid-template-columns: 24px 36px 1fr 120px;
  align-items: center;
  gap: 12px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 8px;
}

.contrib-rank {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.contrib-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 500;
  color: white;
  letter-spacing: 0.04em;
}

.contrib-info {
  display: flex;
  flex-direction: column;
}

.contrib-name {
  font-size: 13px;
  font-weight: 500;
}

.contrib-stats {
  font-size: 11px;
  color: rgb(var(--v-theme-on-surface-variant));
}

.contrib-bar-wrap {
  height: 6px;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 3px;
  overflow: hidden;
}

.contrib-bar {
  height: 100%;
  background: linear-gradient(
    90deg,
    rgba(var(--v-theme-primary), 0.4),
    rgba(var(--v-theme-primary), 0.9)
  );
  border-radius: 3px;
  transition: width 0.2s ease;
}
</style>
