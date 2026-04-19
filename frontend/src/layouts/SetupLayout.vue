<template>
  <div class="setup-gradient d-flex flex-column">
    <v-container class="d-flex flex-column align-center flex-grow-1 py-8">
      <div class="mb-8">
        <BodhiorchardLogo />
      </div>
      <v-sheet
        class="flex-grow-1 w-100"
        color="transparent"
        :max-width="720"
      >
        <router-view />
      </v-sheet>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import BodhiorchardLogo from '@/components/common/BodhiorchardLogo.vue'
</script>
