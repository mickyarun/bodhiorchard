<template>
  <div class="settings-page">
    <!-- Header -->
    <div class="settings-header pa-6 pb-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h5 font-weight-bold">{{ title }}</div>
          <div v-if="subtitle" class="text-body-2 text-medium-emphasis">
            {{ subtitle }}
          </div>
        </div>
        <div class="d-flex ga-2 align-center">
          <slot name="header-actions" />
          <v-btn variant="text" prepend-icon="mdi-arrow-left" :to="{ name: 'settings' }">
            Back to Settings
          </v-btn>
          <v-btn
            color="primary"
            prepend-icon="mdi-content-save-outline"
            :loading="saving"
            :disabled="!valid"
            @click="$emit('save')"
          >
            Save Changes
          </v-btn>
        </div>
      </div>

      <v-alert v-if="error" type="error" variant="tonal" class="mt-4" closable>
        {{ error }}
      </v-alert>
      <v-alert
        v-if="saveSuccess"
        type="success"
        variant="tonal"
        class="mt-4"
        closable
        @click:close="$emit('success-close')"
      >
        Settings saved successfully.
      </v-alert>
    </div>

    <!-- Content -->
    <div class="px-6 pb-6">
      <div v-if="loading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <template v-else>
        <slot />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
  loading: boolean
  saving: boolean
  valid: boolean
  error: string | null
  saveSuccess: boolean
}>()

defineEmits<{
  save: []
  'success-close': []
}>()
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.settings-header {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
</style>
