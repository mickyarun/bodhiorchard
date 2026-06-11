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

<!-- Shared marketing shell: sticky translucent nav + footer wrapping the routed
     pages. Internal links are real <router-link> anchors (crawlable in the SSG
     output); the GitHub link is a real external <a>. The whole site is dark. -->
<template>
  <v-app theme="bodhiorchardDark">
    <header class="landing-nav">
      <div class="landing-nav__inner">
        <router-link to="/" class="landing-nav__brand">
          <img src="/assets/bodhiorchard-logo-sm.png" width="28" height="28" alt="Bodhiorchard" />
          <span class="bo-display">Bodhiorchard</span>
        </router-link>

        <nav class="landing-nav__links">
          <router-link
            v-for="r in navRoutes"
            :key="r.path"
            :to="r.path"
            class="landing-nav__link"
          >
            {{ r.label }}
          </router-link>
        </nav>

        <div class="landing-nav__actions">
          <v-btn
            class="d-none d-sm-inline-flex"
            variant="text"
            size="small"
            prepend-icon="mdi-github"
            :href="GITHUB_URL"
            target="_blank"
            rel="noopener"
          >
            GitHub
          </v-btn>
          <v-btn color="primary" variant="flat" size="small" :href="GITHUB_URL" target="_blank" rel="noopener">
            Get started
          </v-btn>
          <v-app-bar-nav-icon class="d-md-none" @click="drawer = !drawer" />
        </div>
      </div>
    </header>

    <v-navigation-drawer v-model="drawer" location="right" temporary>
      <v-list nav>
        <v-list-item
          v-for="r in navRoutes"
          :key="r.path"
          :to="r.path"
          :title="r.label"
          @click="drawer = false"
        />
        <v-divider class="my-2" />
        <v-list-item :href="GITHUB_URL" target="_blank" rel="noopener" prepend-icon="mdi-github" title="GitHub" />
      </v-list>
    </v-navigation-drawer>

    <v-main>
      <router-view />
    </v-main>

    <LandingFooter />
  </v-app>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import LandingFooter from './components/LandingFooter.vue'
import { LANDING_ROUTES } from './routes-manifest'
import { GITHUB_URL } from './content/site'

// Home is reachable via the brand mark; keep the link bar to the deeper pages.
const navRoutes = LANDING_ROUTES.filter((r) => r.path !== '/')
const drawer = ref(false)
</script>

<style scoped>
.landing-nav {
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(12px);
  background: rgba(7, 19, 10, 0.72);
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
.landing-nav__inner {
  max-width: 1180px;
  margin: 0 auto;
  height: 60px;
  padding: 0 20px;
  display: flex;
  align-items: center;
  gap: 24px;
}
.landing-nav__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  text-decoration: none;
  color: rgb(var(--v-theme-on-surface));
  font-weight: 700;
  font-size: 1.05rem;
  letter-spacing: var(--tracking-display, -0.02em);
}
.landing-nav__links {
  display: none;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
}
.landing-nav__link {
  text-decoration: none;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: var(--text-sm, 0.9rem);
  font-weight: 500;
  padding: 6px 12px;
  border-radius: var(--radius-pill, 999px);
  transition: color 0.18s ease, background 0.18s ease;
}
.landing-nav__link:hover {
  color: rgb(var(--v-theme-on-surface));
  background: rgba(255, 255, 255, 0.04);
}
.landing-nav__link.router-link-active {
  color: rgb(var(--v-theme-primary));
}
.landing-nav__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
@media (min-width: 960px) {
  .landing-nav__links {
    display: flex;
  }
}
</style>
