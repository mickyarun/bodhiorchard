<template>
  <div class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="text-h5 font-weight-bold">Teams</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ store.teams.length }} team{{ store.teams.length !== 1 ? 's' : '' }}
        </div>
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        New Team
      </v-btn>
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Error -->
    <v-alert v-if="store.error" type="error" variant="tonal" class="mb-4" closable>
      {{ store.error }}
    </v-alert>

    <!-- Empty state -->
    <v-card
      v-if="!store.loading && store.teams.length === 0"
      class="pa-12 text-center"
      color="surface"
    >
      <v-icon icon="mdi-account-group-outline" size="64" class="text-medium-emphasis mb-4" />
      <div class="text-h6 mb-2">No teams yet</div>
      <div class="text-body-2 text-medium-emphasis mb-6">
        Create a team to organize your members.
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="showCreateDialog = true">
        Create Team
      </v-btn>
    </v-card>

    <!-- Team cards -->
    <div v-if="!store.loading && store.teams.length > 0" class="teams-grid">
      <v-card
        v-for="team in store.teams"
        :key="team.id"
        class="team-card pa-5"
        color="surface"
      >
        <div class="d-flex align-center justify-space-between mb-3">
          <div class="d-flex align-center ga-2">
            <v-avatar size="32" color="primary" variant="tonal">
              <v-icon icon="mdi-account-group" size="18" />
            </v-avatar>
            <div>
              <div class="text-body-1 font-weight-medium">{{ team.name }}</div>
              <div v-if="team.description" class="text-caption text-medium-emphasis">
                {{ team.description }}
              </div>
            </div>
          </div>

          <v-menu>
            <template #activator="{ props }">
              <v-btn v-bind="props" icon="mdi-dots-vertical" size="small" variant="text" />
            </template>
            <v-list density="compact">
              <v-list-item
                prepend-icon="mdi-account-plus"
                title="Add Member"
                @click="openAddMember(team.id)"
              />
              <v-list-item
                prepend-icon="mdi-delete-outline"
                title="Delete Team"
                class="text-error"
                @click="store.deleteTeam(team.id)"
              />
            </v-list>
          </v-menu>
        </div>

        <v-chip size="x-small" variant="tonal" class="mb-3">
          {{ team.memberCount }} member{{ team.memberCount !== 1 ? 's' : '' }}
        </v-chip>

        <!-- Member list -->
        <div v-if="team.members.length > 0">
          <div
            v-for="member in team.members"
            :key="member.id"
            class="d-flex align-center justify-space-between py-2"
            style="border-top: 1px solid rgba(255,255,255,0.06)"
          >
            <div class="d-flex align-center ga-2">
              <v-avatar size="28" color="surface-variant">
                <span class="text-caption">{{ initials(member.userName) }}</span>
              </v-avatar>
              <div>
                <div class="text-body-2">{{ member.userName }}</div>
                <div class="text-caption text-medium-emphasis">{{ member.email }}</div>
              </div>
            </div>
            <div class="d-flex align-center ga-1">
              <v-chip
                size="x-small"
                :color="member.role === 'lead' ? 'primary' : 'grey'"
                variant="tonal"
              >
                {{ member.role }}
              </v-chip>
              <v-btn
                icon="mdi-close"
                size="x-small"
                variant="text"
                @click="store.removeMember(team.id, member.userId)"
              />
            </div>
          </div>
        </div>
      </v-card>
    </div>

    <!-- Create Team Dialog -->
    <v-dialog v-model="showCreateDialog" max-width="500">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 font-weight-bold mb-4">New Team</div>
        <v-text-field
          v-model="newTeamName"
          label="Team Name"
          placeholder="e.g. Frontend Team"
          autofocus
          class="mb-3"
          @keyup.enter="createTeam"
        />
        <v-textarea
          v-model="newTeamDesc"
          label="Description (optional)"
          rows="2"
          variant="outlined"
        />
        <v-card-actions class="pa-0 mt-2">
          <v-spacer />
          <v-btn variant="text" @click="showCreateDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :disabled="!newTeamName.trim()"
            @click="createTeam"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Add Member Dialog -->
    <v-dialog v-model="showAddMemberDialog" max-width="420">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 font-weight-bold mb-4">Add Member</div>
        <v-text-field
          v-model="memberUserId"
          label="User ID"
          placeholder="Paste user UUID"
          class="mb-3"
        />
        <v-select
          v-model="memberRole"
          :items="['member', 'lead']"
          label="Role"
          variant="outlined"
        />
        <v-card-actions class="pa-0 mt-2">
          <v-spacer />
          <v-btn variant="text" @click="showAddMemberDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :disabled="!memberUserId.trim()"
            @click="addMemberToTeam"
          >
            Add
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useTeamsStore } from '@/stores/teams'

const store = useTeamsStore()

const showCreateDialog = ref(false)
const newTeamName = ref('')
const newTeamDesc = ref('')

const showAddMemberDialog = ref(false)
const addMemberTeamId = ref('')
const memberUserId = ref('')
const memberRole = ref('member')

onMounted(() => {
  store.fetchTeams()
})

function initials(name: string): string {
  return name
    .split(' ')
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2) || '?'
}

async function createTeam(): Promise<void> {
  if (!newTeamName.value.trim()) return
  const team = await store.createTeam(
    newTeamName.value.trim(),
    newTeamDesc.value.trim() || undefined,
  )
  if (team) {
    showCreateDialog.value = false
    newTeamName.value = ''
    newTeamDesc.value = ''
  }
}

function openAddMember(teamId: string): void {
  addMemberTeamId.value = teamId
  memberUserId.value = ''
  memberRole.value = 'member'
  showAddMemberDialog.value = true
}

async function addMemberToTeam(): Promise<void> {
  if (!memberUserId.value.trim()) return
  const ok = await store.addMember(
    addMemberTeamId.value,
    memberUserId.value.trim(),
    memberRole.value,
  )
  if (ok) {
    showAddMemberDialog.value = false
  }
}
</script>

<style scoped>
.teams-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}

.team-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
}
</style>
