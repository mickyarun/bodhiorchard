// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0

// Separate Vite config for the public-facing landing site at bodhiorchard.ai.
// Builds the methodology page as a pre-rendered (vite-ssg) static site.
//
// Project root for this build: frontend/landing-src/
//   (keeps it isolated from the main app's index.html / src/main.ts,
//    which otherwise get pulled in and drag the entire engine + wasm
//    dependency chain along with them.)
//
// Entry:  landing-src/index.html → main.ts → LandingApp.vue → MethodologyStep.vue
// Output: frontend/dist-landing/
// Deploy: npx wrangler pages deploy frontend/dist-landing
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  root: fileURLToPath(new URL('./landing-src', import.meta.url)),
  // publicDir resolves relative to root → landing-src/public/
  // (contains only what the landing site needs; the main app's public/ has
  // ~70MB of 3D assets that must NOT be uploaded to Cloudflare Pages.)
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
    },
  },
  build: {
    outDir: fileURLToPath(new URL('./dist-landing', import.meta.url)),
    emptyOutDir: true,
  },
  // Vuetify imports per-component CSS files (e.g. VChip.css) directly. Node's
  // ESM loader can't import .css without help, so bundle Vuetify into the SSR
  // output instead of leaving it externalised.
  ssr: {
    noExternal: ['vuetify'],
  },
  // vite-ssg extends UserConfig; the field is untyped, hence the directive.
  // @ts-expect-error vite-ssg extension
  ssgOptions: {
    formatting: 'minify',
    script: 'async',
    crittersOptions: false,
  },
})
