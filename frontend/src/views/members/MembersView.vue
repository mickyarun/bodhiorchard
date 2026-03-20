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
      <div class="d-flex align-center ga-2">
        <v-tooltip v-if="githubConnected && !githubOrgConfigured" location="bottom" max-width="280">
          <template #activator="{ props }">
            <span v-bind="props">
              <v-btn variant="tonal" prepend-icon="mdi-github" disabled>
                Import from GitHub
              </v-btn>
            </span>
          </template>
          Set your GitHub organization name in Settings to import members.
        </v-tooltip>
        <v-btn
          v-if="githubConnected && githubOrgConfigured"
          variant="tonal"
          prepend-icon="mdi-github"
          @click="openGithubImport"
        >
          Import from GitHub
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-account-plus-outline" @click="openAddMember">
          Add Member
        </v-btn>
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
    <v-card v-if="!store.loading && store.members.length > 0" color="surface" class="mb-8">
      <v-table density="comfortable">
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>Joined</th>
            <th style="width: 80px;">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="member in store.members"
            :key="member.id"
            :class="{ 'opacity-50': !member.isActive }"
          >
            <td>
              <div class="d-flex align-center ga-2 py-2">
                <v-avatar size="32" color="primary" variant="tonal">
                  <v-img v-if="member.avatarUrl" :src="member.avatarUrl" />
                  <span v-else class="text-caption font-weight-bold">{{ initials(member.name) }}</span>
                </v-avatar>
                <div>
                  <span class="font-weight-medium">{{ member.name }}</span>
                  <div v-if="member.githubUsername" class="text-caption text-medium-emphasis">
                    @{{ member.githubUsername }}
                  </div>
                </div>
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
                :disabled="!member.isActive"
                @update:model-value="(val: string) => store.assignRole(member.id, val)"
              />
              <v-chip v-else size="small" variant="tonal">
                {{ member.roleName || member.role }}
              </v-chip>
            </td>
            <td>
              <v-chip
                :color="member.isActive ? 'success' : 'error'"
                size="small"
                variant="tonal"
              >
                {{ member.isActive ? 'Active' : 'Inactive' }}
              </v-chip>
            </td>
            <td class="text-caption text-medium-emphasis">
              {{ formatDate(member.createdAt) }}
            </td>
            <td>
              <v-tooltip location="top" content-class="text-white bg-grey-darken-3">
                <template #activator="{ props }">
                  <v-btn
                    v-bind="props"
                    :icon="member.isActive ? 'mdi-account-off-outline' : 'mdi-account-check-outline'"
                    size="small"
                    variant="text"
                    :color="member.isActive ? 'warning' : 'success'"
                    @click="store.toggleMemberStatus(member.id)"
                  />
                </template>
                {{ member.isActive ? 'Deactivate member' : 'Reactivate member' }}
              </v-tooltip>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- ─── ROLES SECTION ──────────────────────────────────── -->
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <div class="text-h6 font-weight-bold">Roles</div>
        <div class="text-body-2 text-medium-emphasis">
          System roles are read-only. Create custom roles for your organization.
        </div>
      </div>
      <v-btn
        color="primary"
        variant="tonal"
        prepend-icon="mdi-plus"
        @click="openCreateRole"
      >
        Create Role
      </v-btn>
    </div>

    <v-card color="surface">
      <v-table density="comfortable">
        <thead>
          <tr>
            <th>Name</th>
            <th>Description</th>
            <th>Type</th>
            <th>Permissions</th>
            <th style="width: 100px;">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="role in store.roles" :key="role.id">
            <td class="font-weight-medium">{{ role.name }}</td>
            <td class="text-medium-emphasis">{{ role.description || '—' }}</td>
            <td>
              <v-chip
                :color="role.scopeType === 'SYSTEM' ? 'info' : 'success'"
                size="small"
                variant="tonal"
              >
                {{ role.scopeType === 'SYSTEM' ? 'System' : 'Custom' }}
              </v-chip>
            </td>
            <td class="text-caption text-medium-emphasis">
              {{ role.permissions.length }} permission{{ role.permissions.length !== 1 ? 's' : '' }}
            </td>
            <td>
              <v-btn
                v-if="role.scopeType !== 'SYSTEM'"
                icon="mdi-delete-outline"
                size="small"
                variant="text"
                color="error"
                @click="confirmDeleteRole(role)"
              />
              <span v-else class="text-caption text-medium-emphasis">—</span>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- ─── ADD MEMBER DIALOG ──────────────────────────────── -->
    <v-dialog v-model="addMemberDialog" max-width="480" persistent>
      <v-card>
        <v-card-title class="d-flex align-center justify-space-between">
          <span>Add Member</span>
          <v-btn icon="mdi-close" variant="text" size="small" @click="addMemberDialog = false" />
        </v-card-title>
        <v-card-text>
          <v-text-field
            v-model="newMember.name"
            label="Name"
            variant="outlined"
            density="compact"
            class="mb-3"
            :rules="[v => !!v || 'Name is required']"
          />
          <v-text-field
            v-model="newMember.email"
            label="Email"
            type="email"
            variant="outlined"
            density="compact"
            class="mb-3"
            :rules="[v => !!v || 'Email is required']"
          />
          <v-text-field
            v-model="newMember.password"
            label="Password"
            type="password"
            variant="outlined"
            density="compact"
            class="mb-3"
            :rules="[v => v.length >= 6 || 'Min 6 characters']"
          />
          <v-select
            v-model="newMember.roleId"
            :items="store.roles"
            item-title="name"
            item-value="id"
            label="Role (optional)"
            variant="outlined"
            density="compact"
            clearable
          />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="addMemberDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            :loading="addingMember"
            :disabled="!canAddMember"
            @click="submitAddMember"
          >
            Add
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── GITHUB IMPORT DIALOG ─────────────────────────── -->
    <v-dialog v-model="githubImportDialog" max-width="600" persistent>
      <v-card>
        <v-card-title class="d-flex align-center justify-space-between">
          <div class="d-flex align-center ga-2">
            <v-icon icon="mdi-github" size="22" />
            <span>Import from GitHub</span>
          </div>
          <v-btn icon="mdi-close" variant="text" size="small" @click="githubImportDialog = false" />
        </v-card-title>
        <v-card-text>
          <!-- Loading -->
          <div v-if="githubLoading" class="d-flex justify-center py-8">
            <v-progress-circular indeterminate color="primary" />
          </div>

          <!-- Error -->
          <v-alert v-if="githubError" type="error" variant="tonal" density="compact" class="mb-4">
            {{ githubError }}
          </v-alert>

          <!-- Members list -->
          <template v-if="!githubLoading && githubMembers.length > 0">
            <div class="d-flex align-center justify-space-between mb-2">
              <div class="text-body-2 text-medium-emphasis">
                {{ importableMembers.length }} member{{ importableMembers.length !== 1 ? 's' : '' }} available
                <span v-if="alreadyAddedCount > 0">
                  ({{ alreadyAddedCount }} already added)
                </span>
              </div>
              <v-btn
                variant="text"
                density="compact"
                size="small"
                :disabled="importableMembers.length === 0"
                @click="toggleSelectAll"
              >
                {{ allImportableSelected ? 'Deselect all' : 'Select all' }}
              </v-btn>
            </div>
            <v-list density="compact" class="mb-3" style="max-height: 300px; overflow-y: auto;">
              <v-list-item
                v-for="gh in githubMembers"
                :key="gh.login"
                :disabled="gh.already_added"
                @click="!gh.already_added && toggleGithubUser(gh)"
              >
                <template #prepend>
                  <v-checkbox-btn
                    :model-value="gh.already_added || isGithubUserSelected(gh.login)"
                    :disabled="gh.already_added"
                    @update:model-value="toggleGithubUser(gh)"
                    class="mr-2"
                  />
                  <v-avatar size="32" class="mr-3">
                    <v-img :src="gh.avatar_url" />
                  </v-avatar>
                </template>
                <v-list-item-title>{{ gh.name || gh.login }}</v-list-item-title>
                <v-list-item-subtitle v-if="gh.email" class="text-caption">
                  {{ gh.email }}
                </v-list-item-subtitle>
                <template #append>
                  <v-chip
                    v-if="gh.already_added"
                    size="x-small"
                    variant="tonal"
                    color="success"
                  >
                    Added
                  </v-chip>
                </template>
              </v-list-item>
            </v-list>
          </template>

          <v-alert
            v-if="!githubLoading && !githubError && githubMembers.length === 0 && githubLoaded"
            type="info"
            variant="tonal"
            density="compact"
          >
            No members found in the GitHub organization.
          </v-alert>

          <!-- Default password + role for imported users -->
          <div v-if="selectedGithubUsers.length > 0" class="mt-3">
            <v-divider class="mb-3" />
            <div class="text-body-2 font-weight-medium mb-2">
              {{ selectedGithubUsers.length }} user{{ selectedGithubUsers.length !== 1 ? 's' : '' }} selected
            </div>
            <v-text-field
              v-model="githubImportPassword"
              label="Default password for imported users"
              type="password"
              variant="outlined"
              density="compact"
              class="mb-3"
              :rules="[v => v.length >= 6 || 'Min 6 characters']"
              hint="Users can change this after first login"
              persistent-hint
            />
            <v-select
              v-model="githubImportRoleId"
              :items="store.roles"
              item-title="name"
              item-value="id"
              label="Role for all imported users (optional)"
              variant="outlined"
              density="compact"
              clearable
            />
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="githubImportDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            :loading="importingGithub"
            :disabled="selectedGithubUsers.length === 0 || githubImportPassword.length < 6"
            @click="submitGithubImport"
          >
            Import {{ selectedGithubUsers.length || '' }} User{{ selectedGithubUsers.length !== 1 ? 's' : '' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── CREATE ROLE DIALOG ─────────────────────────────── -->
    <v-dialog v-model="createRoleDialog" max-width="600" persistent>
      <v-card>
        <v-card-title class="d-flex align-center justify-space-between">
          <span>Create Role</span>
          <v-btn icon="mdi-close" variant="text" size="small" @click="createRoleDialog = false" />
        </v-card-title>
        <v-card-text>
          <v-text-field
            v-model="newRole.name"
            label="Role Name"
            variant="outlined"
            density="compact"
            class="mb-3"
            :rules="[v => !!v || 'Name is required']"
          />
          <v-text-field
            v-model="newRole.description"
            label="Description (optional)"
            variant="outlined"
            density="compact"
            class="mb-4"
          />

          <div class="text-subtitle-2 mb-2">Permissions</div>
          <div
            v-for="cat in store.permissionCategories"
            :key="cat.key"
            class="mb-3"
          >
            <div class="text-body-2 font-weight-medium mb-1">{{ cat.name }}</div>
            <div class="d-flex flex-wrap ga-2">
              <v-checkbox
                v-for="perm in cat.permissions"
                :key="perm.id"
                v-model="newRole.permissionIds"
                :value="perm.id"
                :label="perm.name"
                density="compact"
                hide-details
                class="mr-4"
              />
            </div>
          </div>
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="createRoleDialog = false">Cancel</v-btn>
          <v-btn
            color="primary"
            :loading="creatingRole"
            :disabled="!newRole.name"
            @click="submitCreateRole"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- ─── DELETE ROLE CONFIRM ────────────────────────────── -->
    <v-dialog v-model="deleteRoleDialog" max-width="400">
      <v-card>
        <v-card-title>Delete Role</v-card-title>
        <v-card-text>
          Are you sure you want to delete the role
          <strong>{{ roleToDelete?.name }}</strong>?
          Members with this role will need to be reassigned.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="deleteRoleDialog = false">Cancel</v-btn>
          <v-btn color="error" :loading="deletingRole" @click="submitDeleteRole">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMembersStore, type RoleOption } from '@/stores/members'
import { useSettingsStore } from '@/stores/settings'
import api from '@/services/api'

const store = useMembersStore()
const settingsStore = useSettingsStore()

// ─── Add Member ───────────────────────────────
const addMemberDialog = ref(false)
const addingMember = ref(false)
const newMember = ref({ name: '', email: '', password: '', roleId: '' as string })

const githubConnected = computed(() => !!settingsStore.connections.github?.enabled)
const githubOrgConfigured = computed(() => !!settingsStore.connections.github?.org)

function openAddMember() {
  newMember.value = { name: '', email: '', password: '', roleId: '' }
  addMemberDialog.value = true
}

const canAddMember = computed(() => {
  const m = newMember.value
  return m.name && m.email && m.password.length >= 6
})

async function submitAddMember() {
  addingMember.value = true
  const payload: Record<string, string | undefined> = {
    name: newMember.value.name,
    email: newMember.value.email,
    password: newMember.value.password,
  }
  if (newMember.value.roleId) payload.roleId = newMember.value.roleId

  const ok = await store.addMember(payload as { email: string; name: string; password: string; roleId?: string })
  addingMember.value = false
  if (ok) addMemberDialog.value = false
}

// ─── GitHub Import ────────────────────────────
interface GithubMember {
  login: string
  name: string | null
  avatar_url: string
  email: string | null
  already_added: boolean
}

const githubImportDialog = ref(false)
const githubLoading = ref(false)
const githubLoaded = ref(false)
const githubError = ref('')
const githubMembers = ref<GithubMember[]>([])
const selectedGithubUsers = ref<GithubMember[]>([])
const githubImportPassword = ref('')
const githubImportRoleId = ref('')
const importingGithub = ref(false)

const importableMembers = computed(() => githubMembers.value.filter(m => !m.already_added))
const alreadyAddedCount = computed(() => githubMembers.value.filter(m => m.already_added).length)
const allImportableSelected = computed(() =>
  importableMembers.value.length > 0 &&
  selectedGithubUsers.value.length === importableMembers.value.length
)

async function openGithubImport() {
  selectedGithubUsers.value = []
  githubImportPassword.value = ''
  githubImportRoleId.value = ''
  githubError.value = ''
  githubLoaded.value = false
  githubImportDialog.value = true

  // Auto-fetch org members on open
  githubLoading.value = true
  try {
    const { data } = await api.get('/v1/settings/github/org-members')
    githubMembers.value = data
    // Auto-select all importable members
    selectedGithubUsers.value = data.filter((m: GithubMember) => !m.already_added)
  } catch (err: unknown) {
    githubMembers.value = []
    if (err && typeof err === 'object' && 'response' in err) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      githubError.value = axiosErr.response?.data?.detail || 'Failed to fetch GitHub org members.'
    } else {
      githubError.value = 'Failed to connect. Check your GitHub settings.'
    }
  } finally {
    githubLoading.value = false
    githubLoaded.value = true
  }
}

function isGithubUserSelected(login: string): boolean {
  return selectedGithubUsers.value.some(u => u.login === login)
}

function toggleGithubUser(gh: GithubMember) {
  if (gh.already_added) return
  const idx = selectedGithubUsers.value.findIndex(u => u.login === gh.login)
  if (idx >= 0) {
    selectedGithubUsers.value.splice(idx, 1)
  } else {
    selectedGithubUsers.value.push(gh)
  }
}

function toggleSelectAll() {
  if (allImportableSelected.value) {
    selectedGithubUsers.value = []
  } else {
    selectedGithubUsers.value = [...importableMembers.value]
  }
}

async function submitGithubImport() {
  importingGithub.value = true
  let imported = 0
  for (const gh of selectedGithubUsers.value) {
    const ok = await store.addMember({
      name: gh.name || gh.login,
      email: gh.email || `${gh.login}@github.placeholder`,
      password: githubImportPassword.value,
      avatarUrl: gh.avatar_url || undefined,
      githubUsername: gh.login,
      roleId: githubImportRoleId.value || undefined,
    })
    if (ok) imported++
  }
  importingGithub.value = false
  if (imported > 0) {
    githubImportDialog.value = false
    await store.fetchMembers()
  }
}

// ─── Create Role ──────────────────────────────
const createRoleDialog = ref(false)
const creatingRole = ref(false)
const newRole = ref({ name: '', description: '', permissionIds: [] as string[] })

function openCreateRole() {
  newRole.value = { name: '', description: '', permissionIds: [] }
  if (store.permissionCategories.length === 0) {
    store.fetchPermissions()
  }
  createRoleDialog.value = true
}

async function submitCreateRole() {
  creatingRole.value = true
  const ok = await store.createRole({
    name: newRole.value.name,
    description: newRole.value.description || undefined,
    permission_ids: newRole.value.permissionIds,
  })
  creatingRole.value = false
  if (ok) createRoleDialog.value = false
}

// ─── Delete Role ──────────────────────────────
const deleteRoleDialog = ref(false)
const deletingRole = ref(false)
const roleToDelete = ref<RoleOption | null>(null)

function confirmDeleteRole(role: RoleOption) {
  roleToDelete.value = role
  deleteRoleDialog.value = true
}

async function submitDeleteRole() {
  if (!roleToDelete.value) return
  deletingRole.value = true
  const ok = await store.deleteRole(roleToDelete.value.id)
  deletingRole.value = false
  if (ok) deleteRoleDialog.value = false
}

// ─── Helpers ──────────────────────────────────
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

onMounted(() => {
  store.fetchMembers()
  store.fetchRoles()
  settingsStore.fetchConnections()
})
</script>
