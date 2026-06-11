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

<template>
  <footer class="landing-footer">
    <div class="landing-footer__inner">
      <div class="landing-footer__brand">
        <div class="d-flex align-center ga-2 mb-2">
          <img src="/assets/bodhiorchard-logo-sm.png" width="26" height="26" alt="Bodhiorchard" />
          <span class="bo-display landing-footer__wordmark">Bodhiorchard</span>
        </div>
        <p class="landing-footer__tagline bo-display">{{ SITE_TAGLINE }}</p>
      </div>

      <nav class="landing-footer__col">
        <div class="landing-footer__heading">Explore</div>
        <router-link
          v-for="r in LANDING_ROUTES"
          :key="r.path"
          :to="r.path"
          class="landing-footer__link"
        >
          {{ r.label }}
        </router-link>
      </nav>

      <nav class="landing-footer__col">
        <div class="landing-footer__heading">Project</div>
        <a class="landing-footer__link" :href="GITHUB_URL" target="_blank" rel="noopener">GitHub</a>
        <a class="landing-footer__link" href="https://www.apache.org/licenses/LICENSE-2.0" target="_blank" rel="noopener">Apache 2.0 licence</a>
        <router-link class="landing-footer__link" to="/why-bodhiorchard">Why Bodhiorchard</router-link>
      </nav>
    </div>

    <div class="landing-footer__base">
      © 2025–2026 Arun Rajkumar · Apache 2.0 · Self-hosted, your data stays local.
    </div>
  </footer>
</template>

<script setup lang="ts">
import { LANDING_ROUTES } from '../routes-manifest'
import { GITHUB_URL, SITE_TAGLINE } from '../content/site'
</script>

<style scoped>
.landing-footer {
  border-top: 1px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-surface));
  padding: 48px 20px 28px;
}
.landing-footer__inner {
  max-width: 1180px;
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: 40px;
  justify-content: space-between;
}
.landing-footer__brand {
  max-width: 280px;
}
.landing-footer__wordmark {
  font-weight: 700;
  font-size: 1.05rem;
}
.landing-footer__tagline {
  color: rgb(var(--v-theme-primary));
  font-size: 1.05rem;
  margin: 0;
}
.landing-footer__col {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.landing-footer__heading {
  font-size: var(--text-xs, 0.8rem);
  text-transform: uppercase;
  letter-spacing: var(--tracking-label, 0.08em);
  color: rgb(var(--v-theme-on-surface-variant));
  font-weight: 600;
  margin-bottom: 4px;
}
.landing-footer__link {
  text-decoration: none;
  color: rgb(var(--v-theme-ink-2));
  font-size: var(--text-sm, 0.9rem);
  transition: color 0.18s ease;
}
.landing-footer__link:hover {
  color: rgb(var(--v-theme-primary));
}
.landing-footer__base {
  max-width: 1180px;
  margin: 32px auto 0;
  padding-top: 20px;
  border-top: 1px solid rgb(var(--v-theme-rule));
  font-size: var(--text-xs, 0.8rem);
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
