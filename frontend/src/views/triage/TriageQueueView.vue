<template>
  <div class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-2">
      <div class="text-h5 font-weight-bold">Triage Approvals</div>
      <v-btn-toggle v-model="statusFilter" mandatory density="compact" variant="outlined" divided>
        <v-btn value="awaiting_pm" size="small">Awaiting</v-btn>
        <v-btn value="" size="small">All</v-btn>
      </v-btn-toggle>
    </div>
    <div class="text-body-2 text-medium-emphasis mb-6">
      {{ triageStore.sessions.length }} session{{ triageStore.sessions.length !== 1 ? 's' : '' }}
    </div>

    <!-- Loading -->
    <div v-if="triageStore.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error -->
    <v-alert v-else-if="triageStore.error" type="error" variant="tonal" class="mb-4">
      {{ triageStore.error }}
      <template #append>
        <v-btn variant="text" size="small" @click="loadSessions">Retry</v-btn>
      </template>
    </v-alert>

    <!-- Empty state -->
    <v-card
      v-else-if="triageStore.sessions.length === 0"
      class="pa-12 text-center"
      color="surface"
    >
      <v-icon icon="mdi-check-circle-outline" size="64" class="text-medium-emphasis mb-4" />
      <div class="text-h6 mb-2">No sessions to review</div>
      <div class="text-body-2 text-medium-emphasis">
        Feature requests triaged via Slack will appear here for approval.
      </div>
    </v-card>

    <!-- Session cards -->
    <div v-else class="d-flex flex-column ga-3">
      <v-card
        v-for="session in triageStore.sessions"
        :key="session.id"
        color="surface"
        class="session-card"
      >
        <!-- Summary row — always visible -->
        <div
          class="d-flex align-center pa-4 cursor-pointer"
          @click="toggleExpand(session.id)"
        >
          <v-icon
            :icon="expanded === session.id ? 'mdi-chevron-down' : 'mdi-chevron-right'"
            size="20"
            class="mr-3 text-medium-emphasis"
          />

          <!-- Feature name -->
          <div class="flex-grow-1" style="min-width: 0;">
            <div class="text-body-1 font-weight-medium text-truncate">
              {{ session.feature_name || 'Untitled Request' }}
            </div>
            <div class="text-caption text-medium-emphasis text-truncate mt-half">
              {{ session.original_text }}
            </div>
          </div>

          <!-- Requester -->
          <div class="mx-4 text-right" style="min-width: 140px;">
            <span class="slack-mention">{{ displayRequester(session) }}</span>
            <div class="text-caption text-medium-emphasis mt-1">{{ formatDate(session.created_at) }}</div>
          </div>

          <!-- Priority -->
          <v-chip
            v-if="session.priority"
            :color="priorityColor(session.priority)"
            size="small"
            variant="tonal"
            label
            class="mx-2"
            style="min-width: 70px; justify-content: center;"
          >
            {{ session.priority }}
          </v-chip>
          <div v-else class="mx-2" style="min-width: 70px;" />

          <!-- Status -->
          <v-chip
            :color="statusColor(session.status)"
            size="small"
            variant="flat"
            label
            class="mx-2"
            style="min-width: 120px; justify-content: center;"
          >
            {{ statusLabel(session.status) }}
          </v-chip>

          <!-- Actions -->
          <div class="ml-4 d-flex align-center ga-1" style="min-width: 170px; justify-content: flex-end;">
            <template v-if="session.status === 'awaiting_pm'">
              <v-btn
                color="success"
                variant="tonal"
                size="small"
                :loading="actionLoading === session.id + ':approve'"
                @click.stop="confirmApprove(session)"
              >
                Approve
              </v-btn>
              <v-btn
                color="error"
                variant="tonal"
                size="small"
                :loading="actionLoading === session.id + ':reject'"
                @click.stop="confirmReject(session)"
              >
                Reject
              </v-btn>
            </template>
            <router-link
              v-else-if="session.bud_id"
              :to="`/buds/${session.bud_id}`"
              class="text-primary text-decoration-none text-body-2"
              @click.stop
            >
              View BUD
            </router-link>
          </div>
        </div>

        <!-- Expanded detail panel -->
        <v-expand-transition>
          <div v-if="expanded === session.id">
            <v-divider />
            <div class="pa-5 detail-panel">
              <v-row>
                <!-- Left: Original message -->
                <v-col cols="12" md="6">
                  <div class="text-caption text-medium-emphasis font-weight-bold mb-2">
                    ORIGINAL MESSAGE
                  </div>
                  <div class="text-body-2 original-message pa-3 rounded-lg">
                    {{ session.original_text || 'No message content' }}
                  </div>

                  <div class="text-caption text-medium-emphasis font-weight-bold mt-4 mb-2">
                    REQUESTER
                  </div>
                  <div class="text-body-2">
                    <span class="slack-mention">{{ displayRequester(session) }}</span>
                  </div>

                  <div class="text-caption text-medium-emphasis font-weight-bold mt-4 mb-2">
                    SLACK THREAD
                  </div>
                  <div class="text-body-2 text-medium-emphasis">
                    Channel: {{ session.slack_channel }} &middot; Thread: {{ session.thread_ts }}
                  </div>
                </v-col>

                <!-- Right: Triage context -->
                <v-col cols="12" md="6">
                  <div class="text-caption text-medium-emphasis font-weight-bold mb-2">
                    TRIAGE CONTEXT
                  </div>

                  <template v-if="session.triage_context && Object.keys(session.triage_context).length > 0">
                    <div v-if="session.triage_context.business_justification" class="mb-3">
                      <div class="text-caption text-medium-emphasis">Business Justification</div>
                      <div class="text-body-2">{{ session.triage_context.business_justification }}</div>
                    </div>
                    <div v-if="session.triage_context.user_impact" class="mb-3">
                      <div class="text-caption text-medium-emphasis">User Impact</div>
                      <div class="text-body-2">{{ session.triage_context.user_impact }}</div>
                    </div>
                    <div v-if="session.triage_context.urgency" class="mb-3">
                      <div class="text-caption text-medium-emphasis">Urgency</div>
                      <div class="text-body-2">{{ session.triage_context.urgency }}</div>
                    </div>
                    <div v-if="session.triage_context.merchant_name" class="mb-3">
                      <div class="text-caption text-medium-emphasis">Merchant</div>
                      <div class="text-body-2">{{ session.triage_context.merchant_name }}</div>
                    </div>
                    <div v-if="session.triage_context.compliance" class="mb-3">
                      <v-chip color="error" size="small" variant="tonal" label>
                        Compliance / Regulatory
                      </v-chip>
                    </div>
                  </template>
                  <div v-else class="text-body-2 text-medium-emphasis">
                    No triage context available yet.
                  </div>
                </v-col>
              </v-row>
            </div>
          </div>
        </v-expand-transition>
      </v-card>
    </div>

    <!-- Confirmation dialog -->
    <v-dialog v-model="showConfirmDialog" max-width="440">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 font-weight-bold mb-2">
          {{ confirmAction === 'approve' ? 'Approve Feature Request' : 'Reject Feature Request' }}
        </div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          <strong>{{ confirmSession?.feature_name || 'Untitled' }}</strong>
        </div>
        <v-textarea
          v-model="confirmNotes"
          label="Notes (optional)"
          rows="3"
          variant="outlined"
          density="compact"
        />
        <v-card-actions class="pa-0 mt-2">
          <v-spacer />
          <v-btn variant="text" @click="showConfirmDialog = false">Cancel</v-btn>
          <v-btn
            :color="confirmAction === 'approve' ? 'success' : 'error'"
            variant="flat"
            :loading="!!actionLoading"
            @click="executeAction"
          >
            {{ confirmAction === 'approve' ? 'Approve' : 'Reject' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useTriageStore, type TriageSession } from '@/stores/triage'

const triageStore = useTriageStore()

const statusFilter = ref('awaiting_pm')
const expanded = ref<string | null>(null)
const actionLoading = ref('')
const showConfirmDialog = ref(false)
const confirmAction = ref<'approve' | 'reject'>('approve')
const confirmSession = ref<TriageSession | null>(null)
const confirmNotes = ref('')

function loadSessions(): void {
  triageStore.fetchSessions(statusFilter.value || undefined)
}

onMounted(() => loadSessions())

watch(statusFilter, () => loadSessions())

function toggleExpand(id: string): void {
  expanded.value = expanded.value === id ? null : id
}

function displayRequester(session: TriageSession): string {
  // Prefer the resolved display name from the users table
  if (session.requester_display_name) {
    return `@${session.requester_display_name}`
  }
  // Fall back to requester_name if it's not just the Slack ID
  if (session.requester_name && session.requester_name !== session.requester_slack_id) {
    return `@${session.requester_name}`
  }
  // Last resort: show Slack ID in mention format
  return `@${session.requester_slack_id}`
}

function confirmApprove(session: TriageSession): void {
  confirmSession.value = session
  confirmAction.value = 'approve'
  confirmNotes.value = ''
  showConfirmDialog.value = true
}

function confirmReject(session: TriageSession): void {
  confirmSession.value = session
  confirmAction.value = 'reject'
  confirmNotes.value = ''
  showConfirmDialog.value = true
}

async function executeAction(): Promise<void> {
  if (!confirmSession.value) return

  const id = confirmSession.value.id
  const notes = confirmNotes.value.trim() || undefined
  actionLoading.value = `${id}:${confirmAction.value}`

  let success: boolean
  if (confirmAction.value === 'approve') {
    success = await triageStore.approveSession(id, notes)
  } else {
    success = await triageStore.rejectSession(id, notes)
  }

  actionLoading.value = ''
  if (success) {
    showConfirmDialog.value = false
  }
}

function priorityColor(priority: string): string {
  const map: Record<string, string> = {
    critical: 'error',
    high: 'warning',
    medium: 'info',
    low: 'grey',
  }
  return map[priority] || 'grey'
}

function statusColor(status: string): string {
  const map: Record<string, string> = {
    awaiting_pm: 'warning',
    interviewing: 'info',
    checking: 'info',
    approved: 'success',
    rejected: 'error',
    bud_created: 'success',
  }
  return map[status] || 'grey'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    awaiting_pm: 'Awaiting Approval',
    interviewing: 'Interviewing',
    checking: 'Checking',
    approved: 'Approved',
    rejected: 'Rejected',
    bud_created: 'BUD Created',
  }
  return map[status] || status
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.session-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.15s ease;
}

.session-card:hover {
  border-color: rgba(255, 255, 255, 0.15);
}

.mt-half {
  margin-top: 2px;
}

.detail-panel {
  background: rgba(255, 255, 255, 0.02);
}

.original-message {
  background: rgba(255, 255, 255, 0.04);
  white-space: pre-wrap;
  word-break: break-word;
}

.slack-mention {
  background: rgba(29, 155, 209, 0.15);
  color: rgb(29, 155, 209);
  padding: 1px 4px;
  border-radius: 4px;
  font-weight: 500;
  font-size: 0.875rem;
  white-space: nowrap;
}
</style>
