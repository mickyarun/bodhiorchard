<template>
  <v-app>
    <!-- Sidebar -->
    <v-navigation-drawer permanent color="surface" width="240" class="app-sidebar">
      <div class="pa-4 pb-2">
        <FlowDevLogo :size="28" />
      </div>

      <v-list density="compact" nav class="px-2">
        <v-list-item
          prepend-icon="mdi-view-dashboard-outline"
          title="Dashboard"
          to="/dashboard"
          rounded="lg"
        />
        <v-list-item
          prepend-icon="mdi-file-document-outline"
          title="PRDs"
          to="/prds"
          rounded="lg"
        />
        <v-list-item
          prepend-icon="mdi-bug-outline"
          title="Bugs"
          rounded="lg"
          disabled
        />
        <v-list-item
          prepend-icon="mdi-account-group-outline"
          title="Team"
          rounded="lg"
          disabled
        />
      </v-list>

      <template #append>
        <v-divider class="mb-2" />
        <v-list density="compact" nav class="px-2 pb-2">
          <v-list-item
            prepend-icon="mdi-cog-outline"
            title="Settings"
            rounded="lg"
            disabled
          />
        </v-list>
      </template>
    </v-navigation-drawer>

    <!-- Main content -->
    <v-main>
      <router-view />
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import FlowDevLogo from '@/components/common/FlowDevLogo.vue'
</script>

<style scoped>
.app-sidebar {
  border-right: 1px solid rgba(255, 255, 255, 0.06) !important;
}
</style>
