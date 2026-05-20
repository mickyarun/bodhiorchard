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
  <v-card color="surface" class="pa-4">
    <div class="text-subtitle-1 font-weight-bold mb-3">
      <v-icon icon="mdi-information-outline" size="18" class="mr-1" />
      How to Earn XP
    </div>

    <v-table density="compact" class="bg-transparent">
      <thead>
        <tr>
          <th class="text-left">Activity</th>
          <th class="text-right">XP</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="rule in XP_RULES" :key="rule.source">
          <td>
            <v-icon :icon="rule.icon" size="16" class="mr-1" />
            {{ rule.label }}
          </td>
          <td class="text-right font-weight-bold">+{{ rule.xp }}</td>
        </tr>
      </tbody>
    </v-table>

    <div class="text-caption text-medium-emphasis mt-2">
      XP for shipping is split equally among everyone who contributed commits or PRs to a BUD —
      each contributor earns once per stage. What matters is whether your work actually reaches
      develop, UAT, and production. Each stage opts in via the tracked repo's branch config — a
      stage with no branch set awards nothing.
    </div>

    <v-divider class="my-3" />

    <div class="text-subtitle-2 font-weight-bold mb-2">
      <v-icon icon="mdi-fire" size="16" class="mr-1" />
      Streak Multipliers
    </div>
    <div class="d-flex ga-2 flex-wrap mb-3">
      <v-chip v-for="tier in STREAK_TIERS" :key="tier.days" size="small" variant="tonal" color="warning">
        {{ tier.days }}+ days → {{ tier.mult }}x
      </v-chip>
    </div>

    <div class="text-subtitle-2 font-weight-bold mb-2">Levels</div>
    <div class="d-flex ga-2 flex-wrap">
      <v-chip v-for="lvl in LEVELS" :key="lvl.name" size="small" variant="tonal">
        {{ lvl.icon }} {{ lvl.xp }} XP
      </v-chip>
    </div>

    <v-divider class="my-3" />

    <div class="text-subtitle-1 font-weight-bold mb-2">
      <v-icon icon="mdi-star-four-points" size="18" class="mr-1" />
      Skill Points (SP)
    </div>
    <div class="text-caption text-medium-emphasis mb-3">
      SP is a scarce currency earned through quality outcomes. Spend SP to unlock vehicles and
      upgrade your house. <strong>BUD-shipped SP is paid out only when the BUD reaches CLOSED
      status</strong> — a PR merge into a stage branch credits stage XP, but the SP for shipping
      waits for the BUD to move through testing → UAT → PROD → CLOSED. Streak milestones, code
      reviews, and bug-filing SP credit immediately on the triggering event.
    </div>

    <div class="text-caption font-weight-bold mb-1 text-uppercase" style="letter-spacing: 0.05em;">Developer</div>
    <v-table density="compact" class="bg-transparent mb-2">
      <tbody>
        <tr v-for="rule in SP_DEV" :key="rule.label">
          <td class="text-caption">{{ rule.label }}</td>
          <td class="text-right text-caption font-weight-bold" :class="rule.sp > 0 ? 'text-success' : 'text-error'">
            {{ rule.sp > 0 ? '+' : '' }}{{ rule.sp }} SP
          </td>
        </tr>
      </tbody>
    </v-table>

    <div class="text-caption font-weight-bold mb-1 text-uppercase" style="letter-spacing: 0.05em;">QA</div>
    <v-table density="compact" class="bg-transparent mb-2">
      <tbody>
        <tr v-for="rule in SP_QA" :key="rule.label">
          <td class="text-caption">{{ rule.label }}</td>
          <td class="text-right text-caption font-weight-bold" :class="rule.sp > 0 ? 'text-success' : 'text-error'">
            {{ rule.sp > 0 ? '+' : '' }}{{ rule.sp }} SP
          </td>
        </tr>
      </tbody>
    </v-table>

    <div class="text-caption font-weight-bold mb-1 text-uppercase" style="letter-spacing: 0.05em;">PM</div>
    <v-table density="compact" class="bg-transparent mb-2">
      <tbody>
        <tr v-for="rule in SP_PM" :key="rule.label">
          <td class="text-caption">{{ rule.label }}</td>
          <td class="text-right text-caption font-weight-bold" :class="rule.sp > 0 ? 'text-success' : 'text-error'">
            {{ rule.sp > 0 ? '+' : '' }}{{ rule.sp }} SP
          </td>
        </tr>
      </tbody>
    </v-table>

    <div class="text-caption font-weight-bold mb-1 text-uppercase" style="letter-spacing: 0.05em;">Tech Lead</div>
    <v-table density="compact" class="bg-transparent mb-2">
      <tbody>
        <tr v-for="rule in SP_TL" :key="rule.label">
          <td class="text-caption">{{ rule.label }}</td>
          <td class="text-right text-caption font-weight-bold" :class="rule.sp > 0 ? 'text-success' : 'text-error'">
            {{ rule.sp > 0 ? '+' : '' }}{{ rule.sp }} SP
          </td>
        </tr>
      </tbody>
    </v-table>

    <div class="text-caption font-weight-bold mb-1 text-uppercase" style="letter-spacing: 0.05em;">Everyone</div>
    <v-table density="compact" class="bg-transparent">
      <tbody>
        <tr v-for="rule in SP_ALL" :key="rule.label">
          <td class="text-caption">{{ rule.label }}</td>
          <td class="text-right text-caption font-weight-bold text-success">+{{ rule.sp }} SP</td>
        </tr>
      </tbody>
    </v-table>
  </v-card>
</template>

<script setup lang="ts">
const XP_RULES = [
  { source: 'xp_stage_develop', label: 'Merge to develop', xp: '5 ÷ contributors', icon: 'mdi-source-branch' },
  { source: 'xp_stage_uat', label: 'Merge to UAT', xp: '15 ÷ contributors', icon: 'mdi-shield-check-outline' },
  { source: 'xp_stage_prod', label: 'Merge to production', xp: '25 ÷ contributors', icon: 'mdi-rocket-launch-outline' },
  { source: 'review', label: 'Code Review', xp: 20, icon: 'mdi-eye-check-outline' },
  { source: 'bud_completed', label: 'Complete BUD', xp: 50, icon: 'mdi-leaf' },
  { source: 'streak', label: 'Daily Streak', xp: 10, icon: 'mdi-fire' },
  { source: 'quality', label: 'Quality Bonus', xp: '0-30', icon: 'mdi-star' },
]

const STREAK_TIERS = [
  { days: 7, mult: '1.5' },
  { days: 14, mult: '2.0' },
  { days: 30, mult: '2.5' },
]

const LEVELS = [
  { name: 'seedling', xp: 0, icon: '🌱' },
  { name: 'sprout', xp: 100, icon: '🌿' },
  { name: 'sapling', xp: 500, icon: '🌲' },
  { name: 'tree', xp: 1500, icon: '🌳' },
  { name: 'ancient_oak', xp: 5000, icon: '🏔️' },
]

const SP_DEV = [
  { label: 'Code review given', sp: 0.25 },
  { label: 'BUD shipped to PROD', sp: 1.0 },
  { label: 'Quality score > 80%', sp: 0.5 },
  { label: 'Bug found in testing', sp: -0.25 },
  { label: 'Bug found in production', sp: -1.0 },
]

const SP_QA = [
  { label: 'Every 5 testing bugs filed', sp: 1.0 },
  { label: 'Production bug found', sp: 0.5 },
  { label: 'All tests executed for BUD', sp: 0.5 },
  { label: 'False positive bug', sp: -0.25 },
]

const SP_PM = [
  { label: 'BUD shipped to PROD', sp: 2.0 },
  { label: 'BUD approved promptly', sp: 0.25 },
  { label: 'BUD discarded', sp: -0.5 },
]

const SP_TL = [
  { label: 'Code review completed', sp: 0.25 },
  { label: 'Tech arch approved', sp: 0.25 },
  { label: 'Prod bug on reviewed BUD', sp: -0.5 },
]

const SP_ALL = [
  { label: '14-day streak', sp: 1.0 },
  { label: '30-day streak', sp: 2.0 },
]
</script>
