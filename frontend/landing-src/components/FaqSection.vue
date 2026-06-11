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

<!-- Visible FAQ rendered from the same FAQS list that feeds the FAQPage
     JSON-LD, so the structured data always matches on-page content. -->
<template>
  <section>
    <div class="text-overline text-medium-emphasis text-center mb-4">Frequently asked</div>
    <v-expansion-panels variant="accordion" class="faq-panels">
      <v-expansion-panel v-for="faq in FAQS" :key="faq.question">
        <v-expansion-panel-title class="font-weight-medium">{{ faq.question }}</v-expansion-panel-title>
        <v-expansion-panel-text>
          <span class="text-body-2 text-medium-emphasis">{{ faq.answer }}</span>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </section>
</template>

<script setup lang="ts">
import { FAQS } from '../seo/structured-data'
</script>

<style scoped>
.faq-panels {
  max-width: 760px;
  margin: 0 auto;
}
.faq-panels :deep(.v-expansion-panel) {
  background: rgba(255, 255, 255, 0.02) !important;
  border: 1px solid rgb(var(--v-theme-rule));
  margin-bottom: 6px;
}
.faq-panels :deep(.v-expansion-panel)::before {
  box-shadow: none !important;
}
</style>
