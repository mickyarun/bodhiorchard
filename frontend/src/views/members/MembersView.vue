<template>
  <div class="pa-6">
    <!-- Header -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="text-h5 font-weight-bold">Members</div>
        <div class="text-body-2 text-medium-emphasis">
          {{ store.members.length }} member{{ store.members.length !== 1 ? 's' : '' }}
        </div>
      </div>
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
      v-if="!store.loading && store.members.length === 0"
      class="pa-12 text-center"
      color="surface"
    >
      <v-icon icon="mdi-account-group-outline" size="64" class="text-medium-emphasis mb-4" />
      <div class="text-h6 mb-2">No members yet</div>
      <div class="text-body-2 text-medium-emphasis">
        Members will appear here once users are added to the organization.
      </div>
    </v-card>

    <!-- Members table -->
    <v-card v-if="!store.loading && store.members.length > 0" color="surface">
      <v-table density="comfortable">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Joined</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="member in store.members" :key="member.id">
            <td>
              <div class="d-flex align-center ga-2 py-2">
                <v-avatar size="32" color="primary" variant="tonal">
                  <span class="text-caption font-weight-bold">{{ initials(member.name) }}</span>
                </v-avatar>
                <span class="font-weight-medium">{{ member.name }}</span>
              </div>
            </td>
            <td class="text-medium-emphasis">{{ member.email }}</td>
            <td>
              <v-select
                v-if="store.roles.length > 0"
                :model-value="member.roleId"
                :items="store.roles"
                item-title="name"
                item-value="id"
                density="compact"
                variant="outlined"
                hide-details
                style="max-width: 200px;"
                @update:model-value="(val: string) => store.assignRole(member.id, val)"
              />
              <v-chip v-else size="small" variant="tonal">
                {{ member.roleName || member.role }}
              </v-chip>
            </td>
            <td class="text-caption text-medium-emphasis">
              {{ formatDate(member.createdAt) }}
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useMembersStore } from '@/stores/members'

const store = useMembersStore()

onMounted(() => {
  store.fetchMembers()
  store.fetchRoles()
})

function initials(name: string): string {
  return name
    .split(' ')
    .map(w => w[0])
    .join('')
    .toUpperCase()
    .slice(0, 2) || '?'
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-'
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}
</script>
