<template>
  <v-card class="pa-8 card-border-dark" color="surface">
    <div class="d-flex align-center ga-3 mb-6">
      <v-avatar color="primary" size="44">
        <v-icon icon="mdi-domain" size="24" />
      </v-avatar>
      <div>
        <div class="text-h5 font-weight-bold">Organization</div>
        <div class="text-body-2 text-medium-emphasis">Set up your workspace</div>
      </div>
    </div>

    <v-text-field
      v-model="setupStore.state.organization.name"
      label="Organization Name"
      placeholder="Acme Inc."
      prepend-inner-icon="mdi-office-building-outline"
      class="mb-4"
      :rules="[rules.required]"
      @update:model-value="onNameChange"
    />

    <v-text-field
      v-model="setupStore.state.organization.slug"
      label="Slug"
      placeholder="acme-inc"
      prepend-inner-icon="mdi-link-variant"
      hint="Used in URLs. Lowercase letters, numbers, and hyphens only."
      persistent-hint
      class="mb-4"
      :rules="[rules.required, rules.slug]"
    />

    <v-alert
      type="info"
      variant="tonal"
      density="compact"
      icon="mdi-information-outline"
    >
      Bodhigrove supports multi-org setups. You can add more organizations later.
    </v-alert>
  </v-card>
</template>

<script setup lang="ts">
import { useSetupStore } from '@/stores/setup'

const setupStore = useSetupStore()

const rules = {
  required: (v: string) => !!v?.trim() || 'This field is required',
  slug: (v: string) =>
    /^[a-z0-9][a-z0-9-]*$/.test(v) || 'Only lowercase letters, numbers, and hyphens',
}

function onNameChange(value: string | null): void {
  if (value) {
    setupStore.state.organization.slug = setupStore.generateSlug(value)
  }
}
</script>
