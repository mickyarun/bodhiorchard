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
  </v-card>
</template>

<script setup lang="ts">
const XP_RULES = [
  { source: 'commit', label: 'Commit', xp: 5, icon: 'mdi-source-commit' },
  { source: 'pr_opened', label: 'Open PR', xp: 15, icon: 'mdi-source-pull' },
  { source: 'pr_merged', label: 'Merge PR', xp: 25, icon: 'mdi-source-merge' },
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
</script>
