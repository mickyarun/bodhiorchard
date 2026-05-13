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

<script setup lang="ts">
import type { useBudStatusTransitions } from '@/composables/useBudStatusTransitions'

type StatusController = ReturnType<typeof useBudStatusTransitions>

const props = defineProps<{ controller: StatusController }>()

// NOTE: this looks like the props-destructure anti-pattern, but it
// isn't. `controller` is a plain JS object of `Ref`s returned by
// `useBudStatusTransitions` — NOT a reactive props proxy. Each ref
// carries its own dep tracking:
//   - Vue auto-unwraps the destructured refs in the template (they're
//     now top-level <script setup> bindings).
//   - v-model writes flow back through the same Ref instances the
//     parent holds — full bidirectional reactivity.
//   - The composable runs once per parent mount and returns a stable
//     object reference, so the destructure stays valid for the
//     component's lifetime.
// If the parent ever swapped controllers (re-running the composable
// behind the prop), this would silently keep the stale refs. Switch
// to `props.controller.x` template access if that becomes a real
// requirement.
const {
  showNoPRWarningDialog, overrideReasonDialog, overrideReasonText,
  showPendingCasesDialog, pendingCasesTarget, pendingCasesList,
  statusErrorSnackbar, statusErrorMessage,
  confirmNoPRWarning, confirmOverrideStatus, openQATab,
} = props.controller
</script>

<template>
  <div class="bud-status-dialogs">
    <!-- Note: the "Updating status…" progress banner that used to live
         here was redundant with the WS-driven "Assignment / Assigning
         {role}…" banner emitted by BUDWorkflowActions on `skill_invoked`.
         Both fired for the same ~10s window and showed identical copy.
         Keeping only the richer, agent-named WS banner. -->

    <!-- Status Override Reason Dialog (code_review → testing with unmerged PRs) -->
    <v-dialog v-model="overrideReasonDialog" max-width="420">
      <v-card color="surface" class="pa-5">
        <div class="text-subtitle-1 font-weight-medium mb-3">
          Advance to Testing
        </div>
        <div class="text-body-2 text-medium-emphasis mb-3">
          Some PRs aren't merged yet. Please explain why you're manually
          advancing to QA.
        </div>
        <v-textarea
          v-model="overrideReasonText"
          label="Reason (required)"
          rows="3"
          :rules="[v => !!v?.trim() || 'Reason is required']"
        />
        <v-card-actions class="pa-0 mt-2">
          <v-spacer />
          <v-btn variant="text" @click="overrideReasonDialog = false">Cancel</v-btn>
          <v-btn
            color="warning"
            variant="flat"
            :disabled="!overrideReasonText.trim()"
            @click="confirmOverrideStatus"
          >
            Advance
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- No Open PR Warning Dialog (entering code_review with no open PR) -->
    <v-dialog v-model="showNoPRWarningDialog" max-width="420">
      <v-card color="surface" class="pa-5">
        <div class="text-subtitle-1 font-weight-medium mb-3">
          No PR is open to review
        </div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          All PRs are merged or no PR has been raised yet. Code review
          will start only after a PR is raised on GitHub.
        </div>
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="showNoPRWarningDialog = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" @click="confirmNoPRWarning">
            Proceed
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Pending manual test cases dialog.
         Triggered when the tester tries to advance testing → uat (or
         testing → prod on a UAT-disabled org) while any manual case is
         still in pending state. Hard gate — no Proceed button, the
         user must go resolve the cases first. -->
    <v-dialog v-model="showPendingCasesDialog" max-width="500">
      <v-card color="surface" class="pa-5">
        <div class="d-flex align-center ga-2 mb-3">
          <v-icon icon="mdi-clipboard-alert-outline" color="warning" />
          <div class="text-subtitle-1 font-weight-medium">
            Manual test cases still pending
          </div>
        </div>
        <div class="text-body-2 text-medium-emphasis mb-3">
          Cannot advance to
          <strong>{{ pendingCasesTarget }}</strong> —
          {{ pendingCasesList.length }} manual test case{{ pendingCasesList.length === 1 ? '' : 's' }}
          {{ pendingCasesList.length === 1 ? 'is' : 'are' }} still awaiting a result.
        </div>
        <div class="pending-cases-list mb-4">
          <div
            v-for="tc in pendingCasesList.slice(0, 8)"
            :key="tc.id"
            class="pending-case-row"
          >
            <v-icon icon="mdi-circle-outline" size="14" class="mr-2 opacity-60" />
            <strong class="mr-1">{{ tc.id }}</strong>
            <span class="text-truncate">{{ tc.title }}</span>
          </div>
          <div
            v-if="pendingCasesList.length > 8"
            class="text-caption text-medium-emphasis mt-1 pl-6"
          >
            and {{ pendingCasesList.length - 8 }} more…
          </div>
        </div>
        <div class="text-caption text-medium-emphasis mb-4">
          Open the QA tab, mark each case as pass, fail, blocked, or
          skipped, then try again.
        </div>
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" @click="showPendingCasesDialog = false">
            Close
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            prepend-icon="mdi-clipboard-check-outline"
            @click="openQATab"
          >
            Open QA tab
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Backend rejection snackbar (permission denied, race conditions
         where the frontend preempt didn't catch a pending case, etc.)
         so the user sees WHY the PATCH was rejected instead of a blank
         failure. -->
    <v-snackbar
      v-model="statusErrorSnackbar"
      color="error"
      location="bottom"
      :timeout="6000"
      multi-line
    >
      {{ statusErrorMessage }}
      <template #actions>
        <v-btn variant="text" @click="statusErrorSnackbar = false">
          Dismiss
        </v-btn>
      </template>
    </v-snackbar>
  </div>
</template>

<style scoped>
.pending-cases-list {
  max-height: 240px;
  overflow-y: auto;
  padding: 8px 12px;
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 6px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}

.pending-case-row {
  display: flex;
  align-items: center;
  font-size: 13px;
  padding: 3px 0;
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.pending-case-row .text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}
</style>
