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
  Inline phase track rendered inside RepoListRow during a scan. Shows
  the seven per-repo phases as dots (the four cross-repo / global
  phases are rendered once below the list by ScanFinalizationRow).

  Trailing label collapses status into a single human-readable line:
    running   → "running: skill_extraction"
    failed    → "failed: <error message>"
    done      → "done · 4 features · 12s"
    queued    → "queued"
-->
<template>
  <div class="row-track">
    <ol class="row-track__dots">
      <li v-for="phase in PER_REPO_PHASES" :key="phase">
        <ScanChipPopover :phase="phase" :step="stepFor(phase)" />
      </li>
    </ol>
    <div class="row-track__label" :class="`row-track__label--${run.status}`">
      {{ summary }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ScanChipPopover from './ScanChipPopover.vue'
import type { RepoRunRow, ScanPhase, StepRow } from '@/stores/reposcanv2Scans'

// When adding a new phase, classify it here and in ScanFinalizationRow.vue.
// `repo_setup` runs first so the .bodhiorchard worktrees + MCP/hooks land
// before code analysis touches the repo, matching the ordering in
// `app/reposcanv2/scan_runner.py::_DEFAULT_PER_REPO_STAGES`.
const PER_REPO_PHASES: ScanPhase[] = [
  'repo_setup',
  'code_index',
  'skill_extraction',
  'design_system_extract',
  'feature_synthesis',
  // ``extract_routes`` runs after synthesis; only does work on backend
  // repos but emits a chip for every repo so the popover surfaces the
  // skipped-cache reason on non-backend / unchanged-SHA runs.
  'extract_routes',
]

const props = defineProps<{ run: RepoRunRow }>()

function stepFor(phase: ScanPhase): StepRow | null {
  return props.run.steps.find(s => s.phase === phase) ?? null
}

const runningPhase = computed<ScanPhase | null>(() => {
  const step = props.run.steps.find(s => s.status === 'running')
  return step ? step.phase : null
})

const summary = computed(() => {
  switch (props.run.status) {
    case 'running':
      return runningPhase.value ? `running: ${runningPhase.value}` : 'running'
    case 'failed':
      return props.run.error ? `failed: ${props.run.error}` : 'failed'
    case 'done': {
      const features = props.run.feature_count
      return features !== null ? `done · ${features} features` : 'done'
    }
    case 'skipped_unchanged':
      return 'skipped — already up to date'
    case 'cancelled':
      return 'cancelled'
    case 'queued':
    default:
      return 'queued'
  }
})
</script>

<style scoped>
.row-track {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.row-track__dots {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
.row-track__label {
  font-size: 0.74rem;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-family: var(--v-font-family-monospace, monospace);
}
.row-track__label--running { color: rgb(var(--v-theme-primary)); }
.row-track__label--done    { color: rgb(var(--v-theme-success)); }
.row-track__label--failed  { color: rgb(var(--v-theme-error)); }
</style>
