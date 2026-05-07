<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Per-repo classification chip strip on Settings → Code. Up to three chips:

    • Layer chip (color-coded)        — when ``repoLayer`` is set.
    • Tech-stack chip                 — when ``techStack`` is set.
    • DB-flavor chip                  — when ``dbFlavor`` is set.

  Cross-layer link counts (``→ N backends`` / ``← N features``) used to
  live here too but moved off Settings → Code: a per-repo aggregate over
  buggy per-feature writes hid silent regressions. The future Feature
  tab in the frontend will render the actual junction rows instead.

  Renders nothing when the repo has no classification yet — the next
  scan's ``classify_repo`` stage will populate the badges.
-->
<template>
  <div v-if="hasAnyChip" class="repo-classification-chips d-flex align-center ga-2 mt-2">
    <v-chip
      v-if="layerChip"
      :color="layerChip.color"
      size="x-small"
      variant="tonal"
      :prepend-icon="layerChip.icon"
    >
      {{ layerChip.label }}
    </v-chip>
    <v-chip
      v-if="repo.techStack"
      color="grey-darken-1"
      size="x-small"
      variant="tonal"
      prepend-icon="mdi-package-variant"
    >
      {{ repo.techStack }}
    </v-chip>
    <v-chip
      v-if="repo.dbFlavor"
      color="purple"
      size="x-small"
      variant="tonal"
      prepend-icon="mdi-database"
    >
      {{ repo.dbFlavor }}
    </v-chip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RepoInfo, RepoLayer } from '@/types'

const props = defineProps<{ repo: RepoInfo }>()

interface ChipDef {
  label: string
  color: string
  icon: string
}

// Layer → chip color mapping. Picks distinct hues for each
// architectural role so a glance at the row tells the user where the
// repo sits in the org.
const LAYER_CHIPS: Record<RepoLayer, ChipDef> = {
  frontend: { label: 'Frontend', color: 'primary', icon: 'mdi-monitor' },
  backend: { label: 'Backend', color: 'success', icon: 'mdi-server' },
  processor: { label: 'Processor', color: 'info', icon: 'mdi-cog-transfer' },
  batch: { label: 'Batch', color: 'warning', icon: 'mdi-clock-outline' },
  db: { label: 'DB', color: 'purple', icon: 'mdi-database-outline' },
  shared: { label: 'Shared', color: 'grey', icon: 'mdi-package-variant-closed' },
}

const layerChip = computed<ChipDef | null>(() => {
  const layer = props.repo.repoLayer
  if (!layer) return null
  return LAYER_CHIPS[layer] ?? null
})

const hasAnyChip = computed(() => Boolean(
  layerChip.value || props.repo.techStack || props.repo.dbFlavor,
))
</script>
