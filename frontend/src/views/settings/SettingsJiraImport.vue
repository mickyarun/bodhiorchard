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
  <div class="settings-page">
    <!-- Header -->
    <div class="settings-header pa-6 pb-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h5 font-weight-bold">Jira Import</div>
          <div class="text-body-2 text-medium-emphasis">
            Connect to Jira Cloud and import issues into BUDs
          </div>
        </div>
        <v-btn
          v-if="store.isConnected && !wizardOpen"
          color="primary"
          prepend-icon="mdi-import"
          @click="openWizard"
        >
          Import Project
        </v-btn>
      </div>

      <v-alert v-if="store.error" type="error" variant="tonal" class="mt-4" closable>
        {{ store.error }}
      </v-alert>
    </div>

    <!-- Content -->
    <div class="px-6 pb-6">
      <!-- Connection Setup -->
      <v-card class="pa-5 settings-card mb-6" color="surface">
        <div class="d-flex align-center ga-3 mb-4">
          <v-avatar size="36" color="surface-variant" rounded="lg">
            <v-icon icon="mdi-jira" size="22" />
          </v-avatar>
          <div class="flex-grow-1">
            <div class="text-body-2 font-weight-medium">Jira Cloud Connection</div>
            <div class="text-caption text-medium-emphasis">
              API token authentication for Jira Cloud
            </div>
          </div>
          <v-chip
            :color="store.isConnected ? 'success' : 'grey'"
            size="x-small"
            variant="tonal"
          >
            {{ store.isConnected ? 'Connected' : 'Not connected' }}
          </v-chip>
        </div>

        <!-- Setup instructions -->
        <v-alert
          v-if="!store.isConnected"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          <div class="text-body-2 font-weight-medium mb-1">How to get your API token:</div>
          <ol class="text-caption pl-4" style="line-height: 1.6">
            <li>Go to <strong>id.atlassian.com/manage-profile/security/api-tokens</strong></li>
            <li>Click <strong>Create API token</strong> and give it a label (e.g. "Bodhiorchard")</li>
            <li>Copy the generated token and paste it below</li>
          </ol>
        </v-alert>

        <v-text-field
          v-model="store.siteUrl"
          label="Jira Site URL"
          placeholder="https://your-team.atlassian.net"
          prepend-inner-icon="mdi-web"
          variant="outlined"
          density="compact"
          class="mb-3"
          :disabled="store.isConnected"
          hint="Your Atlassian Cloud site URL"
          persistent-hint
        />
        <v-text-field
          v-model="store.email"
          label="Atlassian Account Email"
          placeholder="you@company.com"
          prepend-inner-icon="mdi-email-outline"
          variant="outlined"
          density="compact"
          class="mb-3"
          :disabled="store.isConnected"
          hint="The email address of your Atlassian account"
          persistent-hint
        />
        <v-text-field
          v-model="store.apiToken"
          label="API Token"
          placeholder="Paste your Jira API token here"
          prepend-inner-icon="mdi-key-outline"
          variant="outlined"
          density="compact"
          class="mb-4"
          :type="showToken ? 'text' : 'password'"
          :append-inner-icon="showToken ? 'mdi-eye-off' : 'mdi-eye'"
          :disabled="store.isConnected"
          hint="Generated from Atlassian API token settings"
          persistent-hint
          @click:append-inner="showToken = !showToken"
        />

        <div class="d-flex ga-3">
          <v-btn
            v-if="!store.isConnected"
            color="primary"
            :loading="store.saving"
            :disabled="!canConnect"
            @click="connect"
          >
            Test & Connect
          </v-btn>
          <v-btn
            v-else
            color="error"
            variant="tonal"
            @click="store.disconnect()"
          >
            Disconnect
          </v-btn>
        </div>
      </v-card>

      <!-- Import Wizard -->
      <JiraImportWizard
        v-if="wizardOpen && store.isConnected"
        @close="closeWizard"
        @complete="onImportComplete"
      />

      <!-- Past Import Sessions (only show completed/failed/running — not ready/discovering) -->
      <template v-if="store.isConnected && !wizardOpen">
        <div class="text-h6 font-weight-medium mb-3">Import History</div>

        <div v-if="store.loading" class="d-flex justify-center py-8">
          <v-progress-circular indeterminate color="primary" />
        </div>

        <div v-else-if="importedSessions.length === 0" class="text-center py-8">
          <v-icon icon="mdi-history" size="48" class="mb-4" style="opacity: 0.3" />
          <div class="text-body-2 text-medium-emphasis">
            No imports yet. Click "Import Project" to get started.
          </div>
        </div>

        <div v-else class="d-flex flex-column ga-3">
          <v-card
            v-for="session in importedSessions"
            :key="session.id"
            class="pa-4 settings-card"
            color="surface"
          >
            <div class="d-flex align-center ga-3">
              <v-icon
                :icon="sessionIcon(session.status)"
                :color="sessionColor(session.status)"
                size="20"
              />
              <div class="flex-grow-1">
                <div class="text-body-2 font-weight-medium">
                  {{ session.jiraProjectKey }} — {{ session.jiraProjectName }}
                </div>
                <div class="text-caption text-medium-emphasis">
                  {{ formatDate(session.createdAt) }}
                  <template v-if="session.totalIssues">
                    &middot; {{ session.processedCount }}/{{ session.totalIssues }} issues
                  </template>
                </div>
              </div>
              <v-chip
                :color="sessionColor(session.status)"
                size="x-small"
                variant="tonal"
              >
                {{ session.status }}
              </v-chip>
            </div>

            <!-- Reconciliation summary inline -->
            <div
              v-if="session.result"
              class="mt-3 pt-3 d-flex ga-4"
              style="border-top: 1px solid rgba(255,255,255,0.08)"
            >
              <div class="text-caption">
                <span class="text-success font-weight-medium">
                  {{ session.result.imported.budsCreated }}
                </span> BUDs
              </div>
              <div class="text-caption">
                <span class="text-warning font-weight-medium">
                  {{ session.result.imported.bugsCreated }}
                </span> Bugs
              </div>
              <div class="text-caption">
                <span class="text-medium-emphasis">
                  {{ session.result.skipped.exactDuplicates }}
                </span> skipped
              </div>
              <div v-if="session.result.failed.length" class="text-caption">
                <span class="text-error font-weight-medium">
                  {{ session.result.failed.length }}
                </span> failed
              </div>
            </div>
          </v-card>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useJiraImportStore } from '@/stores/jiraImport'
import JiraImportWizard from '@/components/jira/JiraImportWizard.vue'

const store = useJiraImportStore()

const showToken = ref(false)
const wizardOpen = ref(false)

const canConnect = computed(
  () => store.siteUrl.trim() && store.email.trim() && store.apiToken.trim(),
)

// Only show sessions that actually ran (not abandoned discovery sessions)
const importedSessions = computed(() =>
  store.sessions.filter((s) => ['completed', 'failed', 'running'].includes(s.status)),
)

onMounted(async () => {
  await store.fetchConnectionStatus()
  if (store.isConnected) {
    await store.fetchSessions()
  }
})

async function connect(): Promise<void> {
  const ok = await store.testAndSaveConnection()
  if (ok) {
    await store.fetchSessions()
  }
}

function openWizard(): void {
  store.resetWizard()
  wizardOpen.value = true
}

function closeWizard(): void {
  wizardOpen.value = false
}

async function onImportComplete(): Promise<void> {
  wizardOpen.value = false
  await store.fetchSessions()
}

function sessionIcon(status: string): string {
  const map: Record<string, string> = {
    completed: 'mdi-check-circle',
    failed: 'mdi-alert-circle',
    running: 'mdi-loading',
    pending: 'mdi-clock-outline',
    ready: 'mdi-clock-outline',
    discovering: 'mdi-magnify',
  }
  return map[status] || 'mdi-circle-outline'
}

function sessionColor(status: string): string {
  const map: Record<string, string> = {
    completed: 'success',
    failed: 'error',
    running: 'info',
    pending: 'grey',
    ready: 'warning',
  }
  return map[status] || 'grey'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.settings-header {
  flex-shrink: 0;
}
</style>
