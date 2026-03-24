<template>
  <div>
    <div class="text-center mb-6">
      <v-icon icon="mdi-rocket-launch-outline" size="48" color="primary" class="mb-3" />
      <div class="text-h5 font-weight-bold mb-1">Review & Launch</div>
      <div class="text-body-2 text-medium-emphasis">
        Confirm your configuration and launch Bodhigrove
      </div>
    </div>

    <!-- Organization -->
    <v-card class="pa-5 card-border-dark mb-4" color="surface">
      <div class="d-flex align-center ga-3 mb-3">
        <v-icon icon="mdi-domain" color="primary" size="20" />
        <div class="text-body-1 font-weight-medium">Organization</div>
      </div>
      <v-table density="compact" class="bg-transparent">
        <tbody>
          <tr>
            <td class="text-medium-emphasis" style="width: 140px;">Name</td>
            <td>{{ setupStore.state.organization.name }}</td>
          </tr>
          <tr>
            <td class="text-medium-emphasis">Slug</td>
            <td>
              <code class="text-primary">{{ setupStore.state.organization.slug }}</code>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- Admin -->
    <v-card class="pa-5 card-border-dark mb-4" color="surface">
      <div class="d-flex align-center ga-3 mb-3">
        <v-icon icon="mdi-account-key-outline" color="primary" size="20" />
        <div class="text-body-1 font-weight-medium">Admin Account</div>
      </div>
      <v-table density="compact" class="bg-transparent">
        <tbody>
          <tr>
            <td class="text-medium-emphasis" style="width: 140px;">Name</td>
            <td>{{ setupStore.state.admin.name }}</td>
          </tr>
          <tr>
            <td class="text-medium-emphasis">Email</td>
            <td>{{ setupStore.state.admin.email }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- Repositories -->
    <v-card class="pa-5 card-border-dark mb-4" color="surface">
      <div class="d-flex align-center ga-3 mb-3">
        <v-icon icon="mdi-source-repository" color="primary" size="20" />
        <div class="text-body-1 font-weight-medium">
          Repositories ({{ setupStore.state.sourceCode.repos.length }})
        </div>
      </div>
      <v-table density="compact" class="bg-transparent mb-3">
        <tbody>
          <tr v-for="r in setupStore.state.sourceCode.repos" :key="r.path">
            <td class="text-medium-emphasis" style="width: 180px;">
              <v-icon icon="mdi-source-repository" size="14" class="mr-1" />
              {{ r.path.split('/').pop() }}
            </td>
            <td>
              <v-chip size="x-small" variant="tonal" class="mr-1">{{ r.mainBranch || '?' }}</v-chip>
              <v-chip size="x-small" variant="tonal">{{ r.developBranch || '?' }}</v-chip>
            </td>
          </tr>
          <tr>
            <td class="text-medium-emphasis">AI Engine</td>
            <td>Claude Code</td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <v-alert
      type="info"
      variant="tonal"
      density="compact"
      icon="mdi-information-outline"
      class="mb-6"
    >
      After launch, a scan will start automatically. This usually takes
      15–30 minutes depending on repo size. You can configure GitHub, Slack,
      and other integrations from the Settings page while it runs.
    </v-alert>

    <div class="d-flex justify-center">
      <v-btn
        color="primary"
        size="large"
        prepend-icon="mdi-rocket-launch-outline"
        :loading="setupStore.isSubmitting"
        @click="emit('launch')"
      >
        Launch Bodhigrove
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useSetupStore } from '@/stores/setup'

const setupStore = useSetupStore()

const emit = defineEmits<{
  launch: []
}>()
</script>
